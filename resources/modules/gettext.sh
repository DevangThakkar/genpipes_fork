https://ftp.gnu.org/gnu/gettext/gettext-0.19.8.1.tar.gz


#!/bin/bash
# Exit immediately on error
set -eu -o pipefail

SOFTWARE=gettext
VERSION=0.19.8.1
ARCHIVE=${SOFTWARE}-${VERSION}.tar.gz
ARCHIVE_URL=https://ftp.gnu.org/gnu/$SOFTWARE/$ARCHIVE
SOFTWARE_DIR=$SOFTWARE-$VERSION  

build() {
  cd $INSTALL_DOWNLOAD
  tar zxvf $ARCHIVE

  cd $SOFTWARE_DIR
  ./configure --prefix=$INSTALL_DIR/$SOFTWARE_DIR
  make
  make install
}

module_file() {
echo "\
#%Module1.0
proc ModulesHelp { } {
  puts stderr \"\tMUGQIC - $SOFTWARE \"
}
module-whatis \"$SOFTWARE\"

set             root                $INSTALL_DIR/$SOFTWARE_DIR
prepend-path    PATH                \$root/bin
prepend-path    LIBRARY_PATH        \$root/lib 
prepend-path    LD_LIBRARY_PATH     \$root/lib
prepend-path    C_INCLUDE_PATH      \$root/include
prepend-path    CPATH               \$root/include

"
}

# Call generic module install script once all variables and functions have been set
MODULE_INSTALL_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source $MODULE_INSTALL_SCRIPT_DIR/install_module.sh $@