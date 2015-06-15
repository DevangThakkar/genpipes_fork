#!/bin/bash
# Exit immediately on error
set -eu -o pipefail

################################################################################
# This is a module install script template which should be copied and used for
# consistency between module paths, permissions, etc.
# Only lines marked as "## TO BE ADDED/MODIFIED" should be, indeed, modified.
# Also, once modified, delete this commented-out header and the ## comments
################################################################################

SOFTWARE=KronaTools 
VERSION=2.5 
ARCHIVE=$SOFTWARE-$VERSION.tar
ARCHIVE_URL=http://downloads.sourceforge.net/project/krona/KronaTools%20%28Mac%2C%20Linux%29/$ARCHIVE
SOFTWARE_DIR=$SOFTWARE-$VERSION  

# Specific commands to extract and build the software
# $INSTALL_DIR and $INSTALL_DOWNLOAD have been set automatically
# $ARCHIVE has been downloaded in $INSTALL_DOWNLOAD
build() {
  cd $INSTALL_DOWNLOAD
  tar xvf $ARCHIVE  

  cd $SOFTWARE_DIR
  #./configure --prefix=$INSTALL_DIR/$SOFTWARE_DIR  ## TO BE ADDED AND MODIFIED IF NECESSARY

  # Install software
  cd $INSTALL_DOWNLOAD  ## TO BE ADDED AND MODIFIED IF NECESSARY
  mv -i $SOFTWARE_DIR $INSTALL_DIR/  ## TO BE ADDED AND MODIFIED IF NECESSARY
  cd $INSTALL_DIR/$SOFTWARE_DIR
  echo $INSTALL_DIR/$SOFTWARE_DIR
  ./install.pl --prefix $INSTALL_DIR/$SOFTWARE_DIR
}

module_file() {
echo "\
#%Module1.0
proc ModulesHelp { } {
  puts stderr \"\tMUGQIC - $SOFTWARE \"
}
module-whatis \"$SOFTWARE\"

set             root                $INSTALL_DIR/$SOFTWARE_DIR
prepend-path             PATH                \$root/bin
setenv          KRONA_HOME         \$root/scripts
"
}

# Call generic module install script once all variables and functions have been set
MODULE_INSTALL_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source $MODULE_INSTALL_SCRIPT_DIR/install_module.sh $@
