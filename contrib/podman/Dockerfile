FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PATH=/usr/bin:$PATH \
    HEPYY_PACKAGES_DIR=/opt/hep/packages

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc g++ gfortran \
    cmake ninja-build make pkg-config \
    git curl wget vim nano \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip \
    libopenblas-dev liblapack-dev \
    ca-certificates \
    rsync \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python3 -m pip install --no-cache-dir numpy scipy \
    && python3 -m pip install --no-cache-dir hepyy \
    && hepyy install hepyy-utils/main

RUN python3 -m pip install --no-cache-dir hepyy-workflows \
    && python3 -m pip install --no-cache-dir ipykernel jupyter_client nbconvert seaborn plotly ipywidgets matplotlib \
    && python3 -m pip install --no-cache-dir mdedit diskuh datafileviewer pip-check-resolve \
    && python3 -m pip install --no-cache-dir scipaperlib \
    && python3 -m pip install --no-cache-dir streamlit

ENV PATH=/workspace/.local/bin:$PATH

WORKDIR /workspace

CMD ["/bin/bash"]
