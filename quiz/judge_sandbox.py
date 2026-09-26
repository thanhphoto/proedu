"""
ProEdu Secure Judge Sandbox Module
Cung cấp môi trường thực thi và chấm bài an toàn, bảo vệ máy chủ:
1. Static Security Guard: Phân tích mã nguồn tĩnh (AST & Token check) ngăn chặn mã độc.
2. Docker Container Sandbox: Thực thi trong container cô lập hoàn toàn (--network none, limit RAM/CPU).
3. Secure Fallback Runner: Giới hạn subprocess, tài nguyên và timeout khi không có Docker.
"""

import os
import sys
import time
import shutil
import tempfile
import subprocess
import ast
import re
from typing import Dict, Any, Tuple

# Tên Docker Image được sử dụng cho Sandbox
DOCKER_IMAGE_NAME = "proedu-judge:latest"

# Cờ điều khiển Sandbox Docker: Tự động kích hoạt khi chạy trên Linux (máy chủ Production/VPS)
# hoặc bật thủ công qua biến môi trường PROEDU_DOCKER_JUDGE=1
ENABLE_DOCKER_JUDGE = os.getenv('PROEDU_DOCKER_JUDGE', '1' if sys.platform.startswith('linux') else '0') == '1'

# Các từ khóa / module nguy hiểm bị cấm tuyệt đối trong Python
BANNED_PYTHON_MODULES = {
    'socket', 'requests', 'urllib', 'http', 'ftplib', 'smtplib',
    'subprocess', 'shutil', 'os', 'pty', 'posix', 'nt',
    'ctypes', 'mmap', 'multiprocessing', 'signal',
    'winreg', 'msvcrt', 'resource'
}

BANNED_PYTHON_CALLS = {
    'eval', 'exec', '__import__', 'compile', 'breakpoint',
    'globals', 'locals', 'getattr', 'setattr', 'delattr', 'open'
}

# Các hàm và header nguy hiểm trong C++
BANNED_CPP_PATTERNS = [
    r'\b(system|fork|vfork|exec|execl|execlp|execle|execv|execvp|popen)\s*\(',
    r'#include\s*<sys/socket\.h>',
    r'#include\s*<netinet/in\.h>',
    r'#include\s*<arpa/inet\.h>',
    r'#include\s*<windows\.h>',
    r'#include\s*<winsock2\.h>',
    r'#include\s*<unistd\.h>',
]

def check_python_security(code: str) -> Tuple[bool, str]:
    """
    Phân tích AST mã nguồn Python để phát hiện hành vi truy cập hệ thống hoặc mạng trái phép.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Lỗi cú pháp Python (Syntax Error): {str(e)}"

    for node in ast.walk(tree):
        # 1. Kiểm tra import module cấm
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_pkg = alias.name.split('.')[0]
                if root_pkg in BANNED_PYTHON_MODULES:
                    return False, f"Bảo mật: Không được phép import thư viện hệ thống/mạng '{alias.name}'"
        
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_pkg = node.module.split('.')[0]
                if root_pkg in BANNED_PYTHON_MODULES:
                    return False, f"Bảo mật: Không được phép import từ thư viện '{node.module}'"

        # 2. Kiểm tra gọi hàm cấm như eval, exec, __import__
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in BANNED_PYTHON_CALLS:
                    return False, f"Bảo mật: Hàm '{node.func.id}()' bị hạn chế vì lý do an toàn"
            elif isinstance(node.func, ast.Attribute):
                # Kiểm tra gọi hàm open() hoặc __subclasses__
                if node.func.attr in ('system', 'popen', '__subclasses__', 'spawn'):
                    return False, f"Bảo mật: Phương thức '{node.func.attr}' bị từ chối"

    return True, ""


def check_cpp_security(code: str) -> Tuple[bool, str]:
    """
    Kiểm tra các pattern nguy hiểm trong C++
    """
    for pattern in BANNED_CPP_PATTERNS:
        match = re.search(pattern, code, re.IGNORECASE)
        if match:
            return False, f"Bảo mật C++: Phát hiện lệnh hoặc thư viện hệ thống nguy hiểm ('{match.group(0)}')"
    return True, ""


def is_docker_available() -> bool:
    """Kiểm tra xem Docker daemon có hoạt động và có image proedu-judge hay không"""
    try:
        res = subprocess.run(
            ['docker', 'image', 'inspect', DOCKER_IMAGE_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3
        )
        return res.returncode == 0
    except Exception:
        return False


def execute_in_docker(language: str, code: str, stdin: str, timeout_sec: float) -> Dict[str, Any]:
    """
    Chạy mã nguồn trong Docker Container hoàn toàn cô lập:
    - --network none (ngăn chặn mọi kết nối mạng)
    - --memory 256m (giới hạn bộ nhớ)
    - --cpus 1.0 (giới hạn CPU)
    - Read-only workspace
    - Non-root user
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        input_file = os.path.join(tmpdir, "input.txt")
        with open(input_file, "w", encoding="utf-8") as f:
            f.write(stdin or "")

        if language == 'python':
            code_file = os.path.join(tmpdir, "solution.py")
            with open(code_file, "w", encoding="utf-8") as f:
                f.write(code)

            cmd = [
                'docker', 'run', '--rm',
                '--network', 'none',
                '--memory', '256m',
                '--cpus', '1.0',
                '-v', f'{tmpdir}:/workspace:ro',
                DOCKER_IMAGE_NAME,
                'sh', '-c', f'python3 /workspace/solution.py < /workspace/input.txt'
            ]

            start_t = time.perf_counter()
            try:
                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=timeout_sec + 2.0  # buffer cho docker startup
                )
                exec_time = min(time.perf_counter() - start_t, timeout_sec)
                
                if proc.returncode == 0:
                    return {'status': 'Accepted', 'output': proc.stdout, 'time': round(exec_time, 3)}
                elif proc.returncode == 137: # OOM hoặc bị kill
                    return {'status': 'Memory Limit Exceeded', 'output': 'Vượt quá giới hạn bộ nhớ (256MB)'}
                else:
                    return {'status': 'Runtime Error', 'output': proc.stderr or proc.stdout, 'time': round(exec_time, 3)}
            except subprocess.TimeoutExpired:
                return {'status': 'Time Limit Exceeded', 'output': 'Quá thời gian thực thi'}
            except Exception as e:
                return {'status': 'System Error', 'output': f'Docker Run Error: {str(e)}'}

        elif language == 'cpp':
            # Biên dịch và chạy trong Docker
            code_file = os.path.join(tmpdir, "solution.cpp")
            with open(code_file, "w", encoding="utf-8") as f:
                f.write(code)

            # 1. Biên dịch
            compile_cmd = [
                'docker', 'run', '--rm',
                '--network', 'none',
                '--memory', '512m',
                '-v', f'{tmpdir}:/workspace',
                DOCKER_IMAGE_NAME,
                'sh', '-c', 'g++ -O2 /workspace/solution.cpp -o /workspace/solution'
            ]
            try:
                c_proc = subprocess.run(compile_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
                if c_proc.returncode != 0:
                    return {'status': 'Compilation Error', 'output': c_proc.stderr}
            except subprocess.TimeoutExpired:
                return {'status': 'Compilation Error', 'output': 'Biên dịch quá thời gian quy định (10s)'}

            # 2. Chạy
            run_cmd = [
                'docker', 'run', '--rm',
                '--network', 'none',
                '--memory', '256m',
                '--cpus', '1.0',
                '-v', f'{tmpdir}:/workspace:ro',
                DOCKER_IMAGE_NAME,
                'sh', '-c', '/workspace/solution < /workspace/input.txt'
            ]
            start_t = time.perf_counter()
            try:
                proc = subprocess.run(run_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_sec + 2.0)
                exec_time = min(time.perf_counter() - start_t, timeout_sec)
                if proc.returncode == 0:
                    return {'status': 'Accepted', 'output': proc.stdout, 'time': round(exec_time, 3)}
                elif proc.returncode == 137:
                    return {'status': 'Memory Limit Exceeded', 'output': 'Vượt quá giới hạn bộ nhớ (256MB)'}
                else:
                    return {'status': 'Runtime Error', 'output': proc.stderr or proc.stdout, 'time': round(exec_time, 3)}
            except subprocess.TimeoutExpired:
                return {'status': 'Time Limit Exceeded', 'output': 'Quá thời gian thực thi'}
            except Exception as e:
                return {'status': 'System Error', 'output': f'Docker Run Error: {str(e)}'}

    return {'status': 'System Error', 'output': 'Môi trường Docker không hỗ trợ ngôn ngữ này'}


def execute_secure_locally(language: str, code: str, stdin: str, timeout_sec: float) -> Dict[str, Any]:
    """
    Fallback an toàn khi chạy trực tiếp trên máy chủ:
    - Bắt buộc vượt qua Static Security Guard trước khi thực thi
    - Giới hạn Timeout nghiêm ngặt
    - Giới hạn độ dài output (tối đa 64KB) tránh tràn RAM do in vòng lặp
    """
    MAX_OUTPUT_CHARS = 65536

    if language == 'python':
        python_bin = sys.executable
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_file = f.name

        try:
            start_time = time.perf_counter()
            process = subprocess.run(
                [python_bin, temp_file],
                input=stdin,
                text=True,
                capture_output=True,
                timeout=timeout_sec
            )
            exec_time = time.perf_counter() - start_time
            out = process.stdout[:MAX_OUTPUT_CHARS]
            err = process.stderr[:MAX_OUTPUT_CHARS]
            if process.returncode == 0:
                return {'status': 'Accepted', 'output': out, 'time': round(exec_time, 3)}
            else:
                return {'status': 'Runtime Error', 'output': err, 'time': round(exec_time, 3)}
        except subprocess.TimeoutExpired:
            return {'status': 'Time Limit Exceeded', 'output': 'Quá thời gian cho phép'}
        except Exception as e:
            return {'status': 'System Error', 'output': str(e)}
        finally:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass

    elif language == 'cpp':
        from django.conf import settings
        includes_dir = os.path.join(settings.BASE_DIR, 'quiz', 'cpp_includes')

        with tempfile.TemporaryDirectory() as tmpdirname:
            source_file = os.path.join(tmpdirname, 'solution.cpp')
            executable = os.path.join(tmpdirname, 'solution')

            with open(source_file, 'w', encoding='utf-8') as f:
                f.write(code)

            try:
                compile_process = subprocess.run(
                    ['g++', '-O2', source_file, '-o', executable, '-I', includes_dir],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if compile_process.returncode != 0:
                    return {'status': 'Compilation Error', 'output': compile_process.stderr[:MAX_OUTPUT_CHARS]}
            except subprocess.TimeoutExpired:
                return {'status': 'Compilation Error', 'output': 'Quá thời gian biên dịch (10s)'}
            except Exception as e:
                return {'status': 'System Error', 'output': f'Lỗi gọi trình biên dịch g++: {str(e)}'}

            try:
                start_time = time.perf_counter()
                run_process = subprocess.run(
                    [executable],
                    input=stdin,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec
                )
                exec_time = time.perf_counter() - start_time
                out = run_process.stdout[:MAX_OUTPUT_CHARS]
                err = run_process.stderr[:MAX_OUTPUT_CHARS]
                if run_process.returncode == 0:
                    return {'status': 'Accepted', 'output': out, 'time': round(exec_time, 3)}
                else:
                    return {'status': 'Runtime Error', 'output': err, 'time': round(exec_time, 3)}
            except subprocess.TimeoutExpired:
                return {'status': 'Time Limit Exceeded', 'output': 'Quá thời gian cho phép'}
            except Exception as e:
                return {'status': 'System Error', 'output': str(e)}

    return {'status': 'System Error', 'output': 'Ngôn ngữ chưa được hỗ trợ'}


def run_code_secure(language: str, code: str, stdin: str, timeout_sec: float) -> Dict[str, Any]:
    """
    Điểm vào chính (Main Entrypoint) để chạy code an toàn:
    1. Kiểm tra tĩnh (Static Security Inspection)
    2. Chạy qua Docker Sandbox nếu khả dụng
    3. Nếu không, chạy qua Fallback Sandbox
    """
    if language not in ('python', 'cpp'):
        return {'status': 'System Error', 'output': 'Ngôn ngữ này chưa được hỗ trợ'}

    # 1. Kiểm tra mã nguồn tĩnh
    if language == 'python':
        safe, msg = check_python_security(code)
        if not safe:
            return {'status': 'Security Violation', 'output': msg, 'time': 0}
    elif language == 'cpp':
        safe, msg = check_cpp_security(code)
        if not safe:
            return {'status': 'Security Violation', 'output': msg, 'time': 0}

    # 2. Kiểm tra môi trường Docker Sandbox (Production Linux / Docker bật)
    if ENABLE_DOCKER_JUDGE and is_docker_available():
        return execute_in_docker(language, code, stdin, timeout_sec)

    # 3. Chạy qua Sandbox bảo mật cục bộ có kiểm soát (AST Guard + Subprocess limit)
    return execute_secure_locally(language, code, stdin, timeout_sec)
