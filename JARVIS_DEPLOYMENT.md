# Jarvis Voice Assistant - Deployment Guide

## Overview

Jarvis is a personal AI voice assistant that runs on Raspberry Pi with a Kindle Fire companion display. It provides voice-controlled task management, note-taking, home automation integration, and conversational AI.

**Architecture**:
- **Backend**: Raspberry Pi 5 (Flask + PostgreSQL + Voice I/O)
- **Display**: Kindle Fire HD 10 (Web UI)
- **APIs**: Claude (conversation), ElevenLabs (voice), OpenAI Whisper (transcription)
- **Data**: All stored locally on Raspberry Pi (never leaves your network except for API calls)

## Hardware Requirements

### Minimum
- **Raspberry Pi 5** (4GB RAM recommended, 8GB for comfort)
- **USB Microphone** (noise-canceling for better quality)
- **Speaker** (3.5mm jack or USB speaker)
- **MicroSD Card** (64GB recommended)
- **Power Supply** (27W+ for Pi 5)

### Optional
- **UPS/Battery** (for always-on reliability)
- **Second Raspberry Pi** (for dedicated audio output)
- **Kindle Fire HD 10 2019** (for display)

### Storage
- **PostgreSQL Database**: ~1-5GB for years of conversation/notes
- **Audio files**: ~1-10GB depending on usage
- **System**: ~10GB for OS and dependencies

## Railway Environment Variables

Add these to your Railway project (all required for full functionality):

```env
# Database
DATABASE_URL=postgresql://jarvis_user:PASSWORD@localhost:5432/jarvis
DB_PASSWORD=your_secure_password_here

# Flask
SECRET_KEY=your_flask_secret_key_here
APP_PASSWORD=your_app_login_password

# Voice APIs (get these from respective services)
ANTHROPIC_API_KEY=sk-ant-v0-xxxxx...
ELEVENLABS_API_KEY=sk_xxxxx...
OPENAI_API_KEY=sk-xxxxx...

# Jarvis Configuration
JARVIS_WAKE_WORD=jarvis
JARVIS_VOICE_ID=alistair
MORNING_BRIEFING_TIME="0 6 * * *"  # 6 AM daily
TIMEZONE=America/Denver

# Home Assistant (optional, add if you have HA)
HA_URL=http://home-assistant.local:8123
HA_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Calendar URLs (optional, for existing features)
PERSONAL_ICAL_URL=https://calendar.google.com/calendar/ical/...
CANVAS_ICAL_URL=https://canvas.instructure.com/calendar_feeds/...
SPORTS_ICAL_URL=https://calendar.google.com/calendar/ical/...
```

## Raspberry Pi Setup

### 1. Initial Setup

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker and Docker Compose
sudo apt-get install -y docker.io docker-compose

# Add current user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Install git
sudo apt-get install -y git

# Clone repository
git clone https://github.com/youruser/student-assistant.git
cd student-assistant
```

### 2. Create Environment File

```bash
# Create .env file with Railway variables
cat > .env << 'EOF'
DATABASE_URL=postgresql://jarvis_user:your_password@postgres:5432/jarvis
DB_PASSWORD=your_password
SECRET_KEY=generate-a-random-string
APP_PASSWORD=yourloginpassword
ANTHROPIC_API_KEY=sk-ant-v0-...
ELEVENLABS_API_KEY=sk_...
OPENAI_API_KEY=sk-...
JARVIS_VOICE_ID=alistair
MORNING_BRIEFING_TIME="0 6 * * *"
TIMEZONE=America/Denver
EOF

# Secure the file
chmod 600 .env
```

### 3. Audio Device Setup

```bash
# Check audio devices
arecord -l  # Show recording devices
aplay -l    # Show playback devices

# Install audio utilities
sudo apt-get install -y alsa-utils sox

# Test microphone
arecord -d 5 test.wav
aplay test.wav

# Configure ALSA for your USB microphone (if needed)
# Edit ~/.asoundrc or /etc/asound.conf
```

### 4. Start Jarvis with Docker Compose

```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# Check logs
docker-compose logs -f jarvis

# Verify it's running
curl http://localhost:5000/api/config
```

### 5. Enable Auto-Start on Boot

```bash
# Create systemd service
sudo tee /etc/systemd/system/jarvis.service > /dev/null << 'EOF'
[Unit]
Description=Jarvis Voice Assistant
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/student-assistant
ExecStart=/usr/bin/docker-compose up
Restart=unless-stopped
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable service
sudo systemctl daemon-reload
sudo systemctl enable jarvis
sudo systemctl start jarvis

# Check status
sudo systemctl status jarvis
```

## Kindle Fire Setup

### 1. Network Configuration

1. Connect Kindle to home WiFi
2. Note the Kindle's IP address (Settings > Device Options > About)
3. Ensure it's on same network as Raspberry Pi

### 2. Web Interface

1. Open browser on Kindle: `http://<raspberry-pi-ip>:5000`
2. Login with `APP_PASSWORD`
3. Bookmark the page (add to Home Screen)

### 3. Optimal Display Settings

For Kindle Fire HD 10 2019:
- Font size: Large (Settings > Display & Sounds > Font Size)
- Screen brightness: Auto
- Orientation: Landscape for best use
- Disable screen lock timeout (Security & Privacy)

## Voice Configuration

### ElevenLabs Voice Selection

Alistair (default) is a British voice that works well for Jarvis. To test alternatives:

```bash
# Check available voices
curl -X GET "https://api.elevenlabs.io/v1/voices" \
  -H "xi-api-key: YOUR_KEY"

# Try other British voices:
# - alistair (recommended)
# - callum
# - ollie
# - grace (female alternative)
# - sophia
```

To change voice, update `JARVIS_VOICE_ID` in your `.env` file.

### Wake Word Configuration

Default is "jarvis" (responds to "Jarvis", "hey jarvis", etc.)

To use a different wake word:

```bash
# Update in .env
JARVIS_WAKE_WORD=your_word

# Restart Jarvis
docker-compose restart jarvis
```

**Note**: Wake word detection uses Porcupine (requires API key for "Jarvis"). For custom words, use fallback detection (less accurate but works offline).

## API Keys - Where to Get Them

### 1. Anthropic (Claude API)
- Go to https://console.anthropic.com
- Create account
- Generate API key
- Budget: ~$5-20/month for daily use

### 2. ElevenLabs (Text-to-Speech)
- Go to https://elevenlabs.io
- Sign up (free tier available)
- Generate API key
- Budget: ~$2-10/month depending on voice usage

### 3. OpenAI (Whisper for Speech-to-Text)
- Go to https://platform.openai.com
- Create account
- Generate API key
- Budget: ~$1-5/month for speech transcription

## Testing Jarvis

### 1. Basic API Test

```bash
# Test Flask is running
curl http://localhost:5000/api/config

# Create a note
curl -X POST http://localhost:5000/api/notes \
  -H "Content-Type: application/json" \
  -d '{"content": "Test note", "category": "ideas"}'

# List notes
curl http://localhost:5000/api/notes
```

### 2. Voice Test

```bash
# Test text-to-speech response
curl -X POST http://localhost:5000/api/voice/text \
  -H "Content-Type: application/json" \
  -d '{"text": "Good morning, what time is it?"}'

# Get morning briefing
curl http://localhost:5000/api/voice/briefing
```

### 3. Microphone Test

```bash
# Record 5 seconds from USB mic
arecord -d 5 -f S16_LE -r 16000 test.wav

# Play back
aplay test.wav
```

### 4. Kindle Fire Test

1. Open `http://<pi-ip>:5000` on Kindle
2. Create a task via voice or web interface
3. Check it appears on Kindle display in real-time

## Troubleshooting

### No Audio Output
```bash
# Check audio devices
aplay -l

# Set default output
amixer sset Master unmute
amixer sset Master 100%

# Test speaker
speaker-test -t wav -c 2 -l 1
```

### Microphone Not Working
```bash
# List recording devices
arecord -l

# Check permissions
ls -la /dev/snd/

# Fix permissions if needed
sudo usermod -aG audio pi
```

### PostgreSQL Connection Failed
```bash
# Check database is running
docker-compose logs postgres

# Verify credentials match in .env
# Restart database
docker-compose restart postgres
```

### API Keys Not Working
```bash
# Verify .env file loaded
docker-compose exec jarvis printenv | grep API

# Test API key directly
curl -X GET "https://api.elevenlabs.io/v1/voices" \
  -H "xi-api-key: $ELEVENLABS_API_KEY"
```

### Jarvis Not Starting
```bash
# Check logs
docker-compose logs jarvis

# Check if port 5000 is in use
lsof -i :5000

# Rebuild images
docker-compose build --no-cache
docker-compose up -d
```

## Performance Tips

### 1. Reduce Latency
- Use local faster-whisper fallback for STT (preloaded on Pi)
- Cache frequently used memories (done automatically)
- Use smaller Claude context window for simpler queries

### 2. Save Bandwidth
- Set `MORNING_BRIEFING_TIME` to off-peak hours
- Batch memory extraction (process multiple conversations together)
- Cache briefings (don't regenerate within 1 hour)

### 3. Improve Reliability
- Connect Pi to UPS for always-on operation
- Use wired Ethernet if possible (WiFi can be unstable)
- Monitor logs: `docker-compose logs -f --tail=50`

## Monitoring

### System Health
```bash
# Check resource usage
docker stats

# Monitor Jarvis logs
docker-compose logs -f --tail=100 jarvis

# Check database size
docker-compose exec postgres psql -U jarvis_user -d jarvis -c "SELECT pg_size_pretty(pg_database_size(current_database()));"
```

### Metrics
- Conversation latency: Should be 2-5 seconds for most queries
- Database size: Monitor and archive old messages if grows > 5GB
- Audio quality: Test microphone weekly with background noise

## Backup & Recovery

### Backup Database

```bash
# Backup
docker-compose exec postgres pg_dump -U jarvis_user jarvis > backup_$(date +%Y%m%d).sql

# Restore
docker-compose exec -T postgres psql -U jarvis_user jarvis < backup_20240101.sql
```

### Backup Configuration

```bash
# Backup .env and docker-compose.yml
tar czf jarvis_backup_$(date +%Y%m%d).tar.gz .env docker-compose.yml
```

## Updates

### Update Jarvis Code

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d

# Check everything is working
curl http://localhost:5000/api/config
```

### Update Dependencies

```bash
# Update Python packages
docker-compose exec jarvis pip install --upgrade -r requirements.txt

# Restart
docker-compose restart jarvis
```

## Security Considerations

1. **API Keys**: Store in `.env`, never commit to git
2. **Network**: Keep Jarvis on private network only
3. **Database Password**: Change from default before production use
4. **Firewall**: Only expose port 5000 to trusted devices
5. **Secrets**: Use strong passwords for `APP_PASSWORD` and `SECRET_KEY`

## Next Steps

1. **Test locally** - Get Jarvis running and talking
2. **Tune personality** - Adjust Claude prompts for your preference
3. **Add Home Assistant** - If you have HA, configure `HA_URL` and `HA_TOKEN`
4. **Optimize audio** - Try different microphones and speakers
5. **Customize briefing** - Adjust `MORNING_BRIEFING_TIME` and content

## Support & Debugging

For detailed logs:
```bash
docker-compose logs -f --tail=200 jarvis 2>&1 | tee jarvis_debug.log
```

Check API endpoints:
```bash
# List available endpoints
curl http://localhost:5000/api/config  # Get config
curl http://localhost:5000/api/notes   # List notes
curl http://localhost:5000/api/tasks   # List tasks (if enabled)
```

## Performance Optimization Tips

- Smaller conversations (< 10 exchanges) process faster
- Morning briefing cached for 1 hour (reuse, don't regenerate)
- Use "quick" mode for time-sensitive queries ("what time is it?")
- Off-load heavy computation (long briefings) to low-traffic hours

Enjoy your Jarvis!
