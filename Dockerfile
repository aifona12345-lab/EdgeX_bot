FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc g++ && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/
COPY configs/ ./configs/
COPY scripts/ ./scripts/
COPY run_edgex_grid.py .

RUN mkdir -p logs

ENV EDGEX_BASE_URL=https://pro.edgex.exchange
ENV EDGEX_CONTRACT_ID=10000001
ENV EDGEX_GRID_LEVELS_PER_SIDE=6
ENV EDGEX_GRID_STEP_USD=60
ENV EDGEX_GRID_FIRST_OFFSET_USD=60
ENV EDGEX_GRID_SIZE=0.2
ENV EDGEX_GRID_OP_SPACING_SEC=1.5

CMD ["python", "run_edgex_grid.py"]
