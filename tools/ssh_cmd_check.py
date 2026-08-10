"""Execute SSH via cmd.exe subprocess and check PG data."""
import subprocess, sys, os

# Build SSH command
ssh_cmd = [
    "ssh",
    "-F", r"C:\Users\hmw20\.ssh\jngt_ssh_config",
    "-o", "StrictHostKeyChecking=no",
    "-o", "ConnectTimeout=15",
    "-o", "PasswordAuthentication=yes",
    "-o", "PreferredAuthentications=password",
    "jngt-22012",
    "echo SSH_OK && psql -U postgres -d bf_trend -c \"SELECT count(*) as total_baselines FROM bf_sensor.daily_baselines WHERE baseline_days=30; SELECT variable_name,count(*) as days FROM bf_sensor.daily_baselines WHERE baseline_days=30 AND variable_name IN ('Q_soft_water','P_soft_water','Q_high_pressure_water','P_high_pressure_water','P_medium_pressure_water','ExpansionTankLevel','T_taphole_mean','T_top') GROUP BY variable_name ORDER BY days DESC; SELECT count(*) as n FROM bf_sensor.one_minute_values v JOIN bf_sensor.sensor_registry r ON r.tag_long_name=v.tag_long_name WHERE r.variable_name='Q_soft_water';\""
]

print("Trying SSH via subprocess...")
env = os.environ.copy()
env["SSHPASS"] = "JNgt@2026"

try:
    result = subprocess.run(
        ssh_cmd,
        capture_output=True, text=True, timeout=25,
        env=env
    )
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr[:500] if result.stderr else "")
    print("RC:", result.returncode)
except subprocess.TimeoutExpired:
    print("SSH timed out (25s)")
except Exception as e:
    print(f"Error: {e}")
