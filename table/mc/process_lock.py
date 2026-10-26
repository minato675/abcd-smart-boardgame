"""mqtt_handler.py 중복 실행 방지용 파일 락.

OS 차원의 락(POSIX: fcntl.flock, Windows: msvcrt.locking)을 쓰기 때문에, 프로세스가
정상 종료든 크래시든 죽으면 OS가 자동으로 락을 반환한다 -- 죽은 프로세스가 남긴
lock 파일 때문에 다음 실행이 막히는 걱정(stale lock)은 안 해도 된다.
"""

import atexit
import os
import sys

_LOCK_PATH = "facilitator.lock"
_lock_file = None


def acquire_or_exit() -> None:
    """이미 다른 프로세스가 락을 잡고 있으면 에러 메시지를 출력하고 즉시 종료한다."""
    global _lock_file
    _lock_file = open(_LOCK_PATH, "w")

    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(
            f"[lock] 이미 다른 mqtt_handler.py 프로세스가 실행 중입니다 "
            f"({_LOCK_PATH}). 중복 실행을 방지하기 위해 종료합니다."
        )
        _lock_file.close()
        raise SystemExit(1)

    _lock_file.write(str(os.getpid()))
    _lock_file.flush()
    atexit.register(_release)


def _release() -> None:
    if _lock_file is None:
        return
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_file.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    _lock_file.close()
