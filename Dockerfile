FROM ubuntu:14.04.4

RUN set -xe && \
    echo '#!/bin/sh' > /usr/sbin/policy-rc.d && \
    echo 'exit 101' >> /usr/sbin/policy-rc.d && \
    chmod +x /usr/sbin/policy-rc.d && \
    dpkg-divert --local --rename --add /sbin/initctl && \
    cp -a /usr/sbin/policy-rc.d /sbin/initctl && \
    sed -i 's/^exit.*/exit 0/' /sbin/initctl && \
    echo 'force-unsafe-io' > /etc/dpkg/dpkg.cfg.d/docker-apt-speedup && \
    echo 'DPkg::Post-Invoke { "rm -f /var/cache/apt/archives/*.deb /var/cache/apt/archives/partial/*.deb /var/cache/apt/*.bin || true"; };' > /etc/apt/apt.conf.d/docker-clean && \
    echo 'APT::Update::Post-Invoke { "rm -f /var/cache/apt/archives/*.deb /var/cache/apt/archives/partial/*.deb /var/cache/apt/*.bin || true"; };' >> /etc/apt/apt.conf.d/docker-clean && \
    echo 'Dir::Cache::pkgcache ""; Dir::Cache::srcpkgcache "";' >> /etc/apt/apt.conf.d/docker-clean && \
    echo 'Acquire::Languages "none";' > /etc/apt/apt.conf.d/docker-no-languages && \
    echo 'Acquire::GzipIndexes "true"; Acquire::CompressionTypes::Order:: "gz";' > /etc/apt/apt.conf.d/docker-gzip-indexes

RUN rm -rf /var/lib/apt/lists/*

RUN sed -i 's/^#\s*\(deb.*universe\)$/\1/g' /etc/apt/sources.list

CMD ["/bin/bash"]

WORKDIR /stage

RUN apt-get update && \
    apt-get -y install iptables git mercurial ssh-client curl tree python-pip \
               libssl-dev libcurl4-openssl-dev gettext && \
    apt-get clean

RUN pip install docker-py==1.7.0 requests==2.9.1

ENV DOCKER_VERSION=1.11.2 \
    COMPOSE_VERSION=1.8.0

RUN curl https://get.docker.com/builds/Linux/x86_64/docker-${DOCKER_VERSION}.tgz > docker.tgz && \
    tar -xzf docker.tgz && \
    mv docker/* /usr/bin/ && \
    rmdir docker && \
    rm docker.tgz

ADD dind /usr/local/bin/dind

ADD docker-compose /usr/local/bin/docker-compose

RUN chmod +x /usr/bin/docker* /usr/local/bin/dind /usr/local/bin/docker-compose && \
    rm -fr /var/lib/docker/*

VOLUME /src

VOLUME /var/lib/docker

RUN mkdir -p /root/.ssh/

ADD known_hosts /root/.ssh/known_hosts

ADD run.sh /stage/

ADD builder.py /stage/

RUN chmod a+x /stage/run.sh && \
    chmod a+x /stage/builder.py

ENTRYPOINT ['/stage/run.sh']

