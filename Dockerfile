# Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get full-upgrade

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Instalacija Unicorn i Nginx
# RUN pip install uvicorn
#RUN apt-get update # //&& apt-get install -y nginx

# Kopiranje Nginx konfiguracije (ako postoji nginx.conf)
#COPY nginx.conf /etc/nginx/nginx.conf

# Portovi
EXPOSE 8000

# Pokretanje Unicorn i Nginx
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]