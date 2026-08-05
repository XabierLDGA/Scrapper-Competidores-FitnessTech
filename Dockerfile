FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY . .

# Sin CMD por defecto: docker-compose.yml especifica el comando de cada
# servicio (dashboard sirve con waitress, crawler corre scheduler.py) - la
# misma imagen sirve para ambos porque ambos necesitan el stack completo
# (el boton "Lanzar crawl ahora" del dashboard ejecuta main.py en proceso).
