"""单位转换与校验器单测。"""

from __future__ import annotations

import pytest

from app.core.exceptions import InvalidParamsError, NotFoundError
from app.utils.unit_convert import bytes_to_human, kbps_to_human
from app.utils.validators import validate_device_name, validate_report_filename


def test_bytes_to_human():
    assert bytes_to_human(0) == "0 B"
    assert bytes_to_human(1500).endswith("KB")
    assert bytes_to_human(None) == "—"


def test_kbps_to_human():
    assert kbps_to_human(512) == "512.0 KB/s"
    assert "MB/s" in kbps_to_human(2048)


def test_validate_device_name():
    assert validate_device_name("sda") == "sda"
    assert validate_device_name("/dev/nvme0n1") == "nvme0n1"
    with pytest.raises(InvalidParamsError):
        validate_device_name("../etc")
    with pytest.raises(InvalidParamsError):
        validate_device_name("")


def test_validate_report_filename():
    assert validate_report_filename("health_20260930.html") == "health_20260930.html"
    with pytest.raises(NotFoundError):
        validate_report_filename("../evil.html")
    with pytest.raises(NotFoundError):
        validate_report_filename("diagnostic_x.exe")
