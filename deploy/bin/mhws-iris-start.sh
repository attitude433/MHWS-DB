#!/bin/bash
exec adb -s localhost:5555 shell "su root sh -c \"CLASSPATH=/data/local/tmp/Iris.apk app_process / party.qwer.iris.Main > /dev/null 2>&1 &\""
