import os


def disable_proxy():
    proxy_vars = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ]

    for var in proxy_vars:
        os.environ.pop(var, None)