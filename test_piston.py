import requests

payload = {
    "language": "python",
    "version": "3.10.0",
    "files": [{"content": "print(input().split())"}],
    "stdin": "1 2 3",
    "args": [],
    "compile_timeout": 10000,
    "run_timeout": 5000,
    "compile_memory_limit": -1,
    "run_memory_limit": 256 * 1024 * 1024
}
try:
    res = requests.post("https://piston.website/api/v2/execute", json=payload, timeout=5)
    print("piston.website:", res.status_code)
except Exception as e:
    print("piston.website failed:", e)

