#!/bin/bash
set -e

if [ -S /var/run/docker.sock ]; then
    exec /stage/builder.py
else

    dmsetup mknodes

    # Now, close extraneous file descriptors.
    pushd /proc/self/fd >/dev/null
    for FD in *
    do
        case "$FD" in
        # Keep stdin/stdout/stderr
        [012])
            ;;
        # Nuke everything else
        *)
            eval exec "$FD>&-"
            ;;
        esac
    done
    popd >/dev/null

	udevd --daemon
	docker daemon --host=unix:///var/run/docker.sock > /var/log/docker.log 2>&1 &
	LOOP_LIMIT=60
	for (( i=0; ; i++ )); do
		if [ ${i} -eq ${LOOP_LIMIT} ]; then
			cat /var/log/docker.log
			echo "Failed to start docker (did you use --privileged when running this container?)"
			exit 1
		fi
		sleep 1
		docker version > /dev/null 2>&1 && break
	done
    exec /usr/local/bin/dind /stage/builder.py
fi