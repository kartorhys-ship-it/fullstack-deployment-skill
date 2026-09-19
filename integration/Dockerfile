# Layer B: Native Linux Verification Container (Ubuntu 24.04 LTS)
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install native Linux binaries for syntax and service verification
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    openssh-server \
    sudo \
    systemd \
    python3 \
    python3-venv \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Setup mock user and directories
RUN useradd -m -s /bin/bash deployer && \
    mkdir -p /var/www/webapp/releases /var/www/webapp/shared /var/www/certbot \
    /etc/nginx/snippets /etc/nginx/sites-available /etc/nginx/sites-enabled /etc/nginx/conf.d \
    /etc/systemd/system /etc/ssh/sshd_config.d /etc/sudoers.d

# Copy repository templates for native validation
WORKDIR /app
COPY templates/ /app/templates/
COPY integration/ /app/integration/

# Execute native validation script
CMD ["/bin/bash", "/app/integration/run_integration.sh"]
