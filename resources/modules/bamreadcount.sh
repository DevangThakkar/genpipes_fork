#!/bin/bash
# Exit immediately on error
set -eu -o pipefail

################################################################################
# This is a module install script template which should be copied and used for
# consistency between module paths, permissions, etc.
# Only lines marked as "## TO BE ADDED/MODIFIED" should be, indeed, modified.
# Also, once modified, delete this commented-out header and the ## comments
################################################################################

SOFTWARE=bam-readcount
VERSION=0.7.4
ARCHIVE=v$VERSION.tar.gz
ARCHIVE_URL=https://github.com/genome/bam-readcount/archive/$ARCHIVE

SOFTWARE_DIR=$SOFTWARE-$VERSION

# Specific commands to extract and build the software
# $INSTALL_DIR and $INSTALL_DOWNLOAD have been set automatically
# $ARCHIVE has been downloaded in $INSTALL_DOWNLOAD
build() {
  cd $INSTALL_DOWNLOAD
  tar zxvf $ARCHIVE

  cd $SOFTWARE_DIR
  mkdir repo
  cd repo
  cmake ../ 
  make

  # Install software
  cd $INSTALL_DOWNLOAD
  mv -i $SOFTWARE_DIR $INSTALL_DIR/
}

module_file() {
echo "\
#%Module1.0
proc ModulesHelp { } {
  puts stderr \"\tMUGQIC - $SOFTWARE \"
}
module-whatis \"$SOFTWARE\"

set             root                $INSTALL_DIR/$SOFTWARE_DIR/repo
prepend-path    PATH                \$root
setenv          BAMREADCOUNT_BIN    \$root/bin
"
}

# Call generic module install script once all variables and functions have been set
MODULE_INSTALL_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source $MODULE_INSTALL_SCRIPT_DIR/install_module.sh $@
