"""ffmpeg 能力封装 —— 检测、按需下载、视频转码、时长探测。

设计原则：
- 视频压缩是可选能力。不装 ffmpeg 也能用工具（只压图片），装了才解锁压视频。
- ffmpeg 不打进安装包：体积大且分平台。用到时再从静态构建源下载到本地 bin/。
- 转码保持原扩展名与容器（mp4→mp4 等），避免破坏 pptx 里按扩展名决定的内容类型引用。
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# v1 只转码这几种最常见、容器+H.264 组合安全的格式
SUPPORTED_VIDEO_EXT = {".mp4", ".mov", ".m4v"}

# 各档位的视频参数，与 ppt_compress_engine.QUALITY_TIERS 对齐（下标一致）
# (最大高度, x264 CRF, 预览用估算码率 kbps)
VIDEO_TIERS = [
    (1080, 20, 4000),  # 几乎无损
    (1080, 23, 2500),  # 高质量
    (720, 26, 1500),   # 标准
    (720, 28, 1000),   # 压缩优先
    (480, 30, 600),    # 最小体积
]
AUDIO_KBPS = 128

# 静态构建下载源（稳定/滚动地址）
_DOWNLOADS = {
    "Windows": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    "Linux": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
    "Darwin": "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
}
# 下载包大致体积（仅用于提示）
DOWNLOAD_SIZE_HINT = {"Windows": "约 80 MB", "Linux": "约 40 MB", "Darwin": "约 25 MB"}


# ---------- 路径 ----------
def _exe_name() -> str:
    return "ffmpeg.exe" if os.name == "nt" else "ffmpeg"


def _app_base() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller 打包后
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        t = p / ".write_test"
        t.write_text("x")
        t.unlink()
        return True
    except Exception:
        return False


def bin_dir() -> Path:
    """放下载的 ffmpeg 的目录：优先程序旁的 bin/，否则用户目录。"""
    cand = _app_base() / "bin"
    if _writable(cand):
        return cand
    home = Path.home() / ".toolbox" / "bin"
    home.mkdir(parents=True, exist_ok=True)
    return home


def find_ffmpeg() -> str | None:
    """查找可用的 ffmpeg：环境变量 → 程序旁 bin/ → 系统 PATH。"""
    env = os.environ.get("FFMPEG_BIN")
    if env and Path(env).exists():
        return env
    local = bin_dir() / _exe_name()
    if local.exists():
        return str(local)
    found = shutil.which("ffmpeg")
    return found


def can_download() -> bool:
    return platform.system() in _DOWNLOADS


def download_hint() -> str:
    return DOWNLOAD_SIZE_HINT.get(platform.system(), "")


# ---------- 下载 ----------
def download_ffmpeg(progress_cb=None, log=None) -> str:
    """下载平台对应的静态 ffmpeg 到 bin_dir，返回可执行文件路径。

    progress_cb(downloaded_bytes, total_bytes)；total 未知时为 -1。
    失败抛异常。
    """
    system = platform.system()
    url = _DOWNLOADS.get(system)
    if not url:
        raise RuntimeError(f"暂不支持在 {system} 上自动下载 ffmpeg，请手动安装。")

    if log:
        log(f"开始下载 ffmpeg（{DOWNLOAD_SIZE_HINT.get(system, '')}）…")

    tmpdir = Path(tempfile.mkdtemp(prefix="ffdl_"))
    archive = tmpdir / url.split("/")[-1].split("?")[0]
    if not archive.suffix:
        archive = archive.with_suffix(".zip")

    req = urllib.request.Request(url, headers={"User-Agent": "toolbox/1.0"})
    with urllib.request.urlopen(req) as resp, open(archive, "wb") as f:
        total = int(resp.headers.get("Content-Length", -1) or -1)
        done = 0
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress_cb:
                progress_cb(done, total)

    if log:
        log("下载完成，正在解压…")

    member_path = _extract_ffmpeg(archive, tmpdir)
    dest = bin_dir() / _exe_name()
    shutil.copy2(member_path, dest)
    if os.name != "nt":
        os.chmod(dest, 0o755)
    shutil.rmtree(tmpdir, ignore_errors=True)

    if log:
        log(f"ffmpeg 已就绪：{dest}")
    return str(dest)


def _extract_ffmpeg(archive: Path, out_dir: Path) -> Path:
    """从下载包里取出 ffmpeg 可执行文件，返回其路径。"""
    name = _exe_name()
    if archive.suffix == ".zip" or zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            target = None
            for n in zf.namelist():
                base = n.rsplit("/", 1)[-1]
                if base == name:
                    target = n
                    break
            if target is None:
                raise RuntimeError("下载包中未找到 ffmpeg 可执行文件")
            zf.extract(target, out_dir)
            return out_dir / target
    else:  # tar.xz (Linux)
        import tarfile

        with tarfile.open(archive) as tf:
            target = None
            for m in tf.getmembers():
                if m.name.rsplit("/", 1)[-1] == name and m.isfile():
                    target = m
                    break
            if target is None:
                raise RuntimeError("下载包中未找到 ffmpeg 可执行文件")
            tf.extract(target, out_dir)
            return out_dir / target.name


# ---------- 探测 / 转码 ----------
_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def probe_duration(data: bytes, ext: str, ffmpeg: str) -> float | None:
    """用 ffmpeg -i 解析视频时长（秒）。不依赖 ffprobe。"""
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
        tf.write(data)
        path = tf.name
    try:
        proc = subprocess.run(
            [ffmpeg, "-i", path], capture_output=True, text=True, errors="ignore"
        )
        m = _DUR_RE.search(proc.stderr or "")
        if not m:
            return None
        h, mnt, s = m.groups()
        return int(h) * 3600 + int(mnt) * 60 + float(s)
    except Exception:
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def estimate_size(data: bytes, ext: str, ffmpeg: str, tier_index: int) -> int:
    """快速估算转码后大小（按时长×目标码率），用于滑块预览，不真正转码。"""
    _, _, kbps = VIDEO_TIERS[tier_index]
    dur = probe_duration(data, ext, ffmpeg)
    if dur is None:
        return len(data)
    est = int((kbps + AUDIO_KBPS) * 1000 / 8 * dur)
    return min(len(data), est)


def transcode(data: bytes, ext: str, ffmpeg: str, tier_index: int) -> bytes | None:
    """真实转码，返回新字节；失败或没变小返回 None。保持原扩展名/容器。"""
    max_h, crf, _ = VIDEO_TIERS[tier_index]
    in_dir = Path(tempfile.mkdtemp(prefix="ffin_"))
    inp = in_dir / ("in" + ext)
    out = in_dir / ("out" + ext)
    inp.write_bytes(data)
    try:
        cmd = [
            ffmpeg, "-y", "-i", str(inp),
            "-vf", f"scale=-2:'min(ih,{max_h})'",
            "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
            "-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k",
            "-movflags", "+faststart",
            str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
        if proc.returncode != 0 or not out.exists():
            return None
        new = out.read_bytes()
        return new if len(new) < len(data) else None
    except Exception:
        return None
    finally:
        shutil.rmtree(in_dir, ignore_errors=True)
