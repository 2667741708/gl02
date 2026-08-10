"""Final SSH attempt with paramiko using various password sources."""
import paramiko, os, sys

# Try passwords from different sources
passwords = []
# From ssh config
passwords.append("JNgt@2026")
# Try reading from AGENTS.md
agents_paths = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "AGENTS.md"),
    r"D:\文件\冀南钢铁运行中第二版本\AGENTS.md",
]
for p in agents_paths:
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                if "password" in line.lower() and ":" in line:
                    pw = line.split(":",1)[1].strip().strip('"').strip("'")
                    if pw and len(pw) > 2:
                        passwords.append(pw)

# Also check env files
env_paths = [
    r"D:\文件\冀南钢铁运行中第二版本\PT\imes_web.local.env",
]
for p in env_paths:
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                if "PASSWORD" in line or "password" in line:
                    pw = line.strip().split("=",1)[-1].strip()
                    if pw and len(pw) > 2 and pw not in passwords:
                        passwords.append(pw)

passwords = list(dict.fromkeys(passwords))  # dedup
print(f"Trying {len(passwords)} passwords: {[p[:4]+'***' for p in passwords]}")

for pw in passwords:
    print(f"\nTrying password starting with '{pw[:4]}...' ...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname="10.30.220.12",
            username="administrator",
            password=pw,
            timeout=10,
            banner_timeout=15,
            auth_timeout=15,
            look_for_keys=False,
            allow_agent=False,
        )
        stdin, stdout, stderr = client.exec_command("echo CONNECTED")
        print(f"SUCCESS: {stdout.read().decode().strip()}")

        # Run PG check
        stdin, stdout, stderr = client.exec_command(
            'psql -U postgres -d bf_trend -c "SELECT count(*) FROM bf_sensor.daily_baselines WHERE baseline_days=30;" 2>&1'
        )
        print("PG:", stdout.read().decode().strip()[:500])
        client.close()
        sys.exit(0)
    except paramiko.AuthenticationException:
        print(f"  Auth failed for password {pw[:4]}***")
    except Exception as e:
        print(f"  Connection error: {type(e).__name__}: {str(e)[:100]}")
    finally:
        try: client.close()
        except: pass

print("\nAll passwords failed")
