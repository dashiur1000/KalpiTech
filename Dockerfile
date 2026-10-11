FROM mcr.microsoft.com/dotnet/sdk:8.0-bookworm-slim AS build
WORKDIR /build
COPY global.json ./
COPY src/KalpiTech.Api/KalpiTech.Api.csproj src/KalpiTech.Api/
RUN dotnet restore src/KalpiTech.Api/KalpiTech.Api.csproj
COPY src/KalpiTech.Api/ src/KalpiTech.Api/
RUN dotnet publish src/KalpiTech.Api/KalpiTech.Api.csproj -c Release --no-restore -o /publish -p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:8.0-bookworm-slim
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv tzdata \
    && rm -rf /var/lib/apt/lists/*
COPY tools/data_loader/requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt
WORKDIR /workspace/src/KalpiTech.Api
COPY --from=build /publish/ ./
COPY src/KalpiTech.Api/Data/Sql/ ./Data/Sql/
COPY tools/data_loader/ /workspace/tools/data_loader/
COPY docker/start.py /workspace/docker/start.py
RUN mkdir -p /workspace/.local /workspace/Data && chown -R app:app /workspace/.local
ENV ASPNETCORE_HTTP_PORTS=8080 DataLoader__PythonPath=/opt/venv/bin/python PYTHONUNBUFFERED=1
USER app
EXPOSE 8080
ENTRYPOINT ["/opt/venv/bin/python", "/workspace/docker/start.py"]
