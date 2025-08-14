# Unified Deployment Guide: Tapestry of Legends
## Complete VPS Deployment Instructions

This guide combines pre-deployment preparation with multi-app deployment architecture for the complete Loom of Legends ecosystem.

## Overview

**Current State**: Deploy Tapestry of Legends Discord bot with web interface as part of multi-app architecture
**Architecture**: Discord bot + web interface deployment with nginx routing ready for future applications  
**Target Domain**: loomoflegends.com with subdomain structure (legends.loomoflegends.com for Tapestry of Legends)
**Package**: Use multi-app-deployment.tar.gz with all fixes applied

## Prerequisites

### 1. VPS Requirements
- Ubuntu 20.04+ or similar Linux distribution
- Minimum 2GB RAM, 1 CPU core, 20GB storage
- Root or sudo access
- Domain pointed to VPS IP address

### 2. Required Credentials
- Discord Bot Token
- Domain name (loomoflegends.com)
- Strong database password

## Step-by-Step Deployment

### Step 1: VPS Initial Setup

```bash
# Update system
apt update && apt upgrade -y

# Install essential packages
apt install -y curl wget git nano ufw

# Configure firewall
ufw allow 22    # SSH
ufw allow 80    # HTTP
ufw allow 443   # HTTPS
ufw --force enable

# Create deployment directory
mkdir -p /home/apps
cd /home/apps
```

### Step 2: Upload Application Files

**Option A: Upload Fixed Package (Recommended)**
```bash
# Upload multi-app-deployment.tar.gz to VPS
# Extract to /home/apps/tapestryoflegends/
cd /home/apps
tar -xzf multi-app-deployment.tar.gz
mv extracted-folder-name tapestryoflegends
cd tapestryoflegends
```

**Option B: Git Clone**
```bash
cd /home/apps
git clone https://github.com/ccogswell/tapestryoflegends.git
cd tapestryoflegends
```

### Step 3: Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
rm get-docker.sh

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Verify installation
docker --version
docker-compose --version
```

### Step 4: Configure Multi-App Architecture

```bash
cd /home/apps/tapestryoflegends

# Copy multi-app configuration to parent directory  
cp unified-docker-compose.yml /home/apps/docker-compose.yml

# Setup nginx configuration (clean conf.d directory)
mkdir -p /home/apps/nginx-conf
cp nginx-conf/default.conf /home/apps/nginx-conf/default.conf
```

### Step 5: Environment Configuration

Create `/home/apps/.env`:
```bash
nano /home/apps/.env
```

**Content (replace with your values):**
```env
# Database Configuration
DB_USER=tapestryuser
DB_PASSWORD=YourSecurePassword2025!
DATABASE_URL=postgresql://tapestryuser:YourSecurePassword2025!@postgres:5432/tapestryoflegends

# Application Secrets
SESSION_SECRET=your_32_character_session_secret_here
JWT_SECRET=UCwhogJIGiStPDC1ULhS9VL0cIMgmbLMd+Q+cnRmJZQ=

# Tapestry of Legends (Discord Bot)
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# Domain Configuration
DOMAIN_NAME=loomoflegends.com

# Future Applications (commented out until ready)
# TAPESTRY_HEROS_API_KEY=future_heros_api_key
# TAPESTRY_WORLDS_API_KEY=future_worlds_api_key
```

### Step 6: Deploy Application

```bash
cd /home/apps

# Start services (Discord bot + web interface + database + nginx)
docker-compose up -d

# Verify deployment
docker-compose ps
docker-compose logs tapestryoflegends

# Check specific services
docker-compose logs nginx
docker-compose logs postgres
```

### Step 7: SSL Certificate Setup

```bash
cd /home/apps/tapestryoflegends
chmod +x ssl-setup.sh
./ssl-setup.sh loomoflegends.com
```

## Verification Steps

### Check Bot Status
```bash
# View bot logs
docker-compose logs -f tapestryoflegends

# Check database connection
docker-compose logs postgres

# Verify all containers
docker-compose ps
```

### Expected Log Output
```
tapestryoflegends | INFO: Database tables created/verified successfully
tapestryoflegends | INFO: Quest Keeper#6098 has connected to Discord!
tapestryoflegends | INFO: Force-synced 17 command(s)
tapestryoflegends | INFO: Started participant table update task
tapestryoflegends | INFO: Bot is ready and operational
nginx            | nginx: [notice] start worker processes
```

### Test Applications
1. **Discord Bot**: Test commands `/rp_new`, `/alias`, `/stats` in Discord
2. **Web Interface**: Visit `https://legends.loomoflegends.com` for alias management
3. **Health Checks**: Check `https://legends.loomoflegends.com/health`
4. **Database**: Verify data persistence across bot restarts

## Multi-App URLs

After successful deployment:
- **Main Domain**: `https://loomoflegends.com` (redirects to legends)
- **Tapestry of Legends**: `https://legends.loomoflegends.com` 
- **Health Check**: `https://legends.loomoflegends.com/health`
- **Future Apps**: Ready for heros, worlds, api subdomains

## Troubleshooting

### Common Issues

**Database Connection Errors**
```bash
# Check environment variables
docker-compose exec tapestryoflegends printenv | grep DATABASE

# Test database connectivity
docker-compose exec postgres psql -U tapestryuser -d tapestryoflegends -c "\l"

# Restart services
docker-compose down && docker-compose up -d
```

**Bot Token Issues**
```bash
# Verify token in .env file (mask sensitive parts)
cat /home/apps/.env | grep DISCORD_BOT_TOKEN

# Check bot logs for authentication errors
docker-compose logs tapestryoflegends | grep -i "error\|token\|auth"
```

**Web Interface Issues**
```bash
# Check if port 5001 is accessible
curl -f http://localhost:5001/health

# Verify nginx routing
docker-compose logs nginx | grep legends
```

**Docker Issues**
```bash
# Clean up containers
docker-compose down
docker system prune -f

# Rebuild and restart
docker-compose up -d --build
```

### Performance Optimization

**Database**
```bash
# Monitor database performance
docker-compose exec postgres pg_stat_activity

# Backup database
docker-compose exec postgres pg_dump -U tapestryuser tapestryoflegends > backup.sql
```

**Application Monitoring**
```bash
# Monitor resource usage
docker stats

# Check application health
curl -f https://legends.loomoflegends.com/health
```

## Multi-App Architecture Benefits

This deployment creates infrastructure for the complete Loom of Legends ecosystem:

- **Shared PostgreSQL Database**: All applications use same database instance
- **Nginx Reverse Proxy**: Ready for subdomain routing
- **SSL Certificate Management**: Automated certificate handling
- **Docker Orchestration**: Easy service management and scaling

## Future Application Integration

When ready to add other applications:

1. **Tapestry of Heros**: Add service definition to docker-compose.yml
2. **Tapestry of Worlds**: Add service definition to docker-compose.yml  
3. **Web Frontend**: Add React/Vue frontend service
4. **API Backend**: Add unified API gateway service

Each application will automatically share:
- Database access
- SSL certificates
- Domain routing
- Environment variables

## Security Considerations

- All sensitive data in environment variables
- Database isolated within Docker network
- Firewall configured for essential ports only
- SSL certificates automatically renewed
- No unnecessary services exposed

## Maintenance

### Regular Updates
```bash
cd /home/apps
docker-compose pull
docker-compose up -d
```

### Backup Database
```bash
docker-compose exec postgres pg_dump -U tapestryuser tapestryoflegends > backup.sql
```

### Monitor Logs
```bash
docker-compose logs -f
```

## Support

For deployment issues:
1. Check Docker container status: `docker-compose ps`
2. Review application logs: `docker-compose logs [service_name]`
3. Verify environment configuration: `cat /home/apps/.env`
4. Test network connectivity: `docker-compose exec tapestryoflegends ping postgres`

This unified deployment provides a production-ready Discord bot with infrastructure prepared for the complete Loom of Legends ecosystem expansion.