#!/bin/bash

#Convert all CSVs to XLS, since labyamcs apps will have filled it when this docker container is assembled
/scripts/mkmdb.sh /mdb_shared /yamcs_cont/yamcs_repo/src/main/yamcs/mdb

#Run YAMCS server with the generated XLS
cd /yamcs_cont/yamcs_repo
mvn yamcs:run

