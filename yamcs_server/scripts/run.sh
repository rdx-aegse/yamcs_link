#!/bin/bash

#Wait for yamcs_link to generate the mdbs
/scripts/waitforfiles.sh /mdb_shared 

#Convert all CSVs to XLS, since labyamcs apps will have filled it when this docker container is assembled
/scripts/mkmdb.sh /mdb_shared /mdb_shared

#Run YAMCS server with the generated XLS
cd /yamcs_cont/yamcs_repo
mvn yamcs:run

