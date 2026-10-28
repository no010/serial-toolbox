import os

import pytest

# GUI 测试在无显示环境下运行
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class StubCh341Dll:
    """WCH CH341 厂商库的最小替身：记录调用，按 present 集合应答"""

    def __init__(self, present=(0x50,), stream_ok=True):
        self.present = set(present)
        self.stream_ok = stream_ok
        self.calls: list[tuple[bytes, int]] = []
        self.speed_mode: int | None = None
        self.opened = False
        self.closed = False

    def CH341OpenDevice(self, index):
        self.opened = True
        return 1

    def CH341CloseDevice(self, index):
        self.closed = True
        return True

    def CH341SetStream(self, index, mode):
        self.speed_mode = mode.value
        return True

    def CH341StreamI2C(self, index, write_len, write_buf, read_len, read_buf):
        frame = bytes(write_buf[: write_len.value]) if write_buf else b""
        n = read_len.value
        if read_buf is not None and n:
            for i in range(n):
                read_buf[i] = 0xA5
        self.calls.append((frame, n))
        addr = frame[0] >> 1 if frame else None
        return self.stream_ok and addr in self.present


@pytest.fixture
def stub_ch341():
    return StubCh341Dll
