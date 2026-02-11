FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

COPY railway_requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p .streamlit
RUN echo '[server]\nheadless = true\naddress = "0.0.0.0"\nport = 5000\nenableCORS = false\n' > .streamlit/config.toml

CMD ["python3", "combined_sports_runner.py"]
