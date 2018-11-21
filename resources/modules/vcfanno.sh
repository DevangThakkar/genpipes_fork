#!/bin/bash
# Exit immediately on error
set -eu -o pipefail

SOFTWARE="vcfanno"
VERSION="0.2.9"
ARCHIVE=${SOFTWARE}_linux64
ARCHIVE_URL=https://github.com/brentp/${SOFTWARE}/releases/download/v${VERSION}/${ARCHIVE}
SOFTWARE_DIR=${SOFTWARE}-${VERSION}


# Specific commands to extract and build the software
# $INSTALL_DIR and $INSTALL_DOWNLOAD have been set automatically
# $ARCHIVE has been downloaded in $INSTALL_DOWNLOAD
build() {
  cd $INSTALL_DOWNLOAD
  chmod a+x $ARCHIVE
  mkdir $SOFTWARE_DIR
  cp $ARCHIVE ${SOFTWARE_DIR}/${SOFTWARE}

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

set             root                $INSTALL_DIR/$SOFTWARE_DIR
prepend-path    PATH                \$root ;  
"
}

# Call generic module install script once all variables and functions have been set
MODULE_INSTALL_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source $MODULE_INSTALL_SCRIPT_DIR/install_module.sh $@
