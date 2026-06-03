# libhackrf 2024.02.01

## DEPENDENCY

1. fftw ```sudo apt install libfftw3-dev```
2. libusb runtime (installed via msys or static build. see example DLIBUSB_INCLUDE_DIR )
3. sphinx (for docs) ```sudo apt-get install python3-sphinx && sudo apt install python3-sphinx-rtd-theme```

## My compiler info
```
Using built-in specs.
COLLECT_GCC=gcc
COLLECT_LTO_WRAPPER=/usr/libexec/gcc/x86_64-linux-gnu/14/lto-wrapper
OFFLOAD_TARGET_NAMES=nvptx-none:amdgcn-amdhsa
OFFLOAD_TARGET_DEFAULT=1
Target: x86_64-linux-gnu
Configured with: ../src/configure -v --with-pkgversion='Ubuntu 14.2.0-19ubuntu2' --with-bugurl=file:///usr/share/doc/gcc-14/README.Bugs --enable-languages=c,ada,c++,go,d,fortran,objc,obj-c++,m2,rust --prefix=/usr --with-gcc-major-version-only --program-suffix=-14 --program-prefix=x86_64-linux-gnu- --enable-shared --enable-linker-build-id --libexecdir=/usr/libexec --without-included-gettext --enable-threads=posix --libdir=/usr/lib --enable-nls --enable-bootstrap --enable-clocale=gnu --enable-libstdcxx-debug --enable-libstdcxx-time=yes --with-default-libstdcxx-abi=new --enable-libstdcxx-backtrace --enable-gnu-unique-object --disable-vtable-verify --enable-plugin --enable-default-pie --with-system-zlib --enable-libphobos-checking=release --with-target-system-zlib=auto --enable-objc-gc=auto --enable-multiarch --disable-werror --enable-cet --with-arch-32=i686 --with-abi=m64 --with-multilib-list=m32,m64,mx32 --enable-multilib --with-tune=generic --enable-offload-targets=nvptx-none=/build/gcc-14-C86vgL/gcc-14-14.2.0/debian/tmp-nvptx/usr,amdgcn-amdhsa=/build/gcc-14-C86vgL/gcc-14-14.2.0/debian/tmp-gcn/usr --enable-offload-defaulted --without-cuda-driver --enable-checking=release --build=x86_64-linux-gnu --host=x86_64-linux-gnu --target=x86_64-linux-gnu --with-build-config=bootstrap-lto-lean --enable-link-serialization=2
Thread model: posix
Supported LTO compression algorithms: zlib zstd
gcc version 14.2.0 (Ubuntu 14.2.0-19ubuntu2) 
```

## Build step commands

1. Download libhackrf 2024.02.01 source code
2. Open MSYS MINGW64

3. Build via cmake

> WARNING! EDIT DLIBUSB_INCLUDE_DIR DLIBUSB_LIBRARIES DFFTW_INCLUDE_DIR DFFTW_LIBRARIES DCMAKE_INSTALL_PREFIX

```sh
mkdir -p build && cd ./build
cmake .. -G "Unix Makefiles" -DLIBUSB_INCLUDE_DIR="/home/d-moskovskikh/aes-source/libusb-build/linux/v1.0.29/x86_64/include/libusb-1.0" -DLIBUSB_LIBRARIES="/home/d-moskovskikh/aes-source/libusb-build/linux/v1.0.29/x86_64/lib/libusb-1.0.so" -DCMAKE_INSTALL_PREFIX="/home/d-moskovskikh/aes-source/libhackrf-build/linux/2024.02.01/x86_64/" -DCMAKE_POLICY_VERSION_MINIMUM=3.5
```

4. Build library
```sh
make
```

5. Install library

> WARNING! WRITE YOUR DESTDIR

```sh
make install
```

6. Configure UDEV rules 

Find & copy 53-hackrf.rules file 
```sh 
sudo cp ./53-hackrf.rules /etc/udev/rules.d/53-hackrf.rules
```

```sh
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Using
