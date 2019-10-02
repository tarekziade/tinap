openssl genrsa -des3 -out private_key.pem 2048
openssl req -new -sha256 -key private_key.pem -out server.csr
openssl req -x509 -sha256 -days 365 -key private_key.pem -in server.csr -out server.pem
