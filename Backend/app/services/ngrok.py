def get_ngrok_tcp_endpoint():
    import requests

    try:
        res = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
        data = res.json()

        for tunnel in data.get("tunnels", []):
            if tunnel.get("proto") == "tcp":
                url = tunnel["public_url"].replace("tcp://", "")
                host, port = url.split(":")
                return host, int(port)

        # No TCP tunnel found
        return None, None

    except Exception as e:
        print("⚠️ Ngrok not running:", str(e))
        return None, None