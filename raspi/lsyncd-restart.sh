#!/bin/bash
kill `cat /tmp/lsyncd.pid``
lsyncd lsyncd.conf


