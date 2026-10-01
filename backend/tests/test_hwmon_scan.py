"""hwmon pwm 通道扫描：fan_channel 配对与缺转速计的通道（control/hwmon_driver.py）。"""

from __future__ import annotations

from app.services.control.hwmon_driver import scan_channels


def test_scan_channels_pairs_fan_channel(tmp_path):
    chip = tmp_path / "hwmon5"
    chip.mkdir()
    (chip / "name").write_text("nct6795", encoding="ascii")
    (chip / "pwm2").write_text("90", encoding="ascii")
    (chip / "pwm2_enable").write_text("1", encoding="ascii")
    (chip / "fan2_input").write_text("1339", encoding="ascii")
    (chip / "pwm3").write_text("90", encoding="ascii")  # 无 fan3_input

    channels = scan_channels(tmp_path)
    by_pwm = {c["pwm_channel"]: c for c in channels}
    assert set(by_pwm) == {2, 3}
    assert by_pwm[2]["fan_channel"] == 2
    assert by_pwm[2]["current_rpm"] == 1339
    assert by_pwm[2]["chip"] == "nct6795"
    assert by_pwm[3]["fan_channel"] is None  # 无转速计的通道不猜配对
    assert by_pwm[2]["writable"] is True
