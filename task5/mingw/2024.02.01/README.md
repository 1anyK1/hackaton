# libhackrf 2024.02.01

## DEPENDENCY

1. pthreads ```pacman -Su mingw-w64-x86_64-libwinpthread```
2. fftw ```pacman -Su mingw-w64-x86_64-fftw```
3. libusb runtime (installed via msys or static build. see example DLIBUSB_INCLUDE_DIR )

## My compiler info
```
Using built-in specs.
COLLECT_GCC=C:\WorkPrograms\sdk\msys2\mingw64\bin\gcc.exe
COLLECT_LTO_WRAPPER=C:/WorkPrograms/sdk/msys2/mingw64/bin/../lib/gcc/x86_64-w64-mingw32/15.2.0/lto-wrapper.exe
Target: x86_64-w64-mingw32
Configured with: ../gcc-15.2.0/configure --prefix=/mingw64 --with-local-prefix=/mingw64/local --with-native-system-header-dir=/mingw64/include --libexecdir=/mingw64/lib --enable-bootstrap --enable-checking=release --with-arch=nocona --with-tune=generic --enable-mingw-wildcard --enable-languages=c,lto,c++,fortran,ada,objc,obj-c++,jit --enable-shared --enable-static --enable-libatomic --enable-threads=posix --enable-graphite --enable-fully-dynamic-string --enable-libstdcxx-backtrace=yes --enable-libstdcxx-filesystem-ts --enable-libstdcxx-time --disable-libstdcxx-pch --enable-lto --enable-libgomp --disable-libssp --disable-multilib --disable-rpath --disable-win32-registry --disable-nls --disable-werror --disable-symvers --with-libiconv --with-system-zlib --with-gmp=/mingw64 --with-mpfr=/mingw64 --with-mpc=/mingw64 --with-isl=/mingw64 --with-pkgversion='Rev8, Built by MSYS2 project' --with-bugurl=https://github.com/msys2/MINGW-packages/issues --with-gnu-as --with-gnu-ld --with-libstdcxx-zoneinfo=yes --disable-libstdcxx-debug --enable-plugin --with-boot-ldflags=-static-libstdc++ --with-stage1-ldflags=-static-libstdc++
Thread model: posix
Supported LTO compression algorithms: zlib zstd
gcc version 15.2.0 (Rev8, Built by MSYS2 project)
```

## Build step commands

1. Download libhackrf 2024.02.01 source code
2. Open MSYS MINGW64

3. Build via cmake

> WARNING! EDIT DLIBUSB_INCLUDE_DIR DLIBUSB_LIBRARIES DFFTW_INCLUDE_DIR DFFTW_LIBRARIES DCMAKE_INSTALL_PREFIX

```sh
mkdir -p build && cd ./build
cmake .. -G "MinGW Makefiles" -DLIBUSB_INCLUDE_DIR="/c/Develop/git-repos/aes-source/libusb-build/mingw/v1.0.29/include/libusb-1.0" -DLIBUSB_LIBRARIES="/c/Develop/git-repos/aes-source/libusb-build/mingw/v1.0.29/lib/libusb-1.0.a" -DFFTW_INCLUDE_DIR="/c/WorkPrograms/sdk/msys2/mingw64/include" -DFFTW_LIBRARIES="/c/WorkPrograms/sdk/msys2/mingw64/lib/libfftw3f.a" -DCMAKE_INSTALL_PREFIX="/c/Develop/git-repos/aes-source/libhackrf-build/mingw/2024.02.01" -DCMAKE_POLICY_VERSION_MINIMUM=3.5
```

4. Build library
```sh
mingw32-make
```

5. Install library

> WARNING! WRITE YOUR DESTDIR

```sh
mingw32-make install
```

## Using
