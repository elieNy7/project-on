import urllib.request
print(urllib.request.urlopen("http://127.0.0.1:8080/obs").read().decode('utf-8'))
