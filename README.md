# Morrigan

A system for downloading BBC radio shows, transcribing them, and storing them in a format suitable for future analysis.

## Overview

This project provides an end-to-end solution for:
- Discovering and downloading BBC radio programs
- Storing audio files on a NAS or local storage
- Transcribing audio content using Whisper
- Managing and accessing the resulting data through a web dashboard

The system uses a Raspberry Pi for coordination and downloading, and a Desktop PC with GPU for transcription processing, with shared NAS storage.

## System Requirements

### Hardware Requirements
- Raspberry Pi 5 (4GB+ RAM recommended)
- Desktop PC with NVIDIA GPU (RTX series recommended)
- NAS device with sufficient storage
- Network connectivity between all devices

### Software Requirements
- Raspberry Pi OS (64-bit)
- NVIDIA drivers and CUDA toolkit on Desktop PC
- Docker and Docker Compose
- Python 3.9+

## Quick Start

### 1. Clone this repository
```bash
git clone https://github.com/yourusername/bbc-radio-processor.git
cd bbc-radio-processor
```

### 2. Configure your NAS
Follow the instructions in [docs/setup.md](docs/setup.md) to set up your NAS.

### 3. Set up your Raspberry Pi
```bash
cd scripts
chmod +x setup_pi.sh
./setup_pi.sh
```

### 4. Configure NAS mounting
```bash
chmod +x mount_nas.sh
./mount_nas.sh
```

### 5. Set up your Desktop PC
```bash
chmod +x setup_desktop.sh
./setup_desktop.sh
```

### 6. Configure the system
Copy the example configuration file and edit it:
```bash
cd config
cp config.yaml.example config.yaml
nano config.yaml
```

### 7. Start the services
```bash
cd docker
docker-compose up -d
```

### 8. Access the dashboard
Open a web browser and go to `http://<raspberry-pi-ip>:8501`

## Development

### Setting up a development environment
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -e .  # Install package in development mode
```

### Running tests
```bash
pytest
```

### Building documentation
```bash
cd docs
make html
```

## Architecture Overview

This system consists of several modules:

1. **Downloader**: Discovers and downloads BBC radio content
2. **Storage**: Manages audio files, transcriptions, and metadata
3. **Transcription**: Converts audio to text
4. **API/Interface**: Provides control and access to the system

For more details, see [docs/architecture.md](docs/architecture.md).

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- [get_iplayer](https://github.com/get-iplayer/get_iplayer) for BBC content downloading
- [Whisper](https://github.com/openai/whisper) for audio transcription
- [Streamlit](https://streamlit.io/) for the dashboard interface
