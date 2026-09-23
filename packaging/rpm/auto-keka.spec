# We ship prebuilt binaries (Chromium + compiled wheels) and a venv untouched.
# Disable rpm's default post-install munging so it can't strip/relocate/corrupt
# them or spend minutes bytecompiling the venv:
%global debug_package %{nil}
%global __brp_strip %{nil}
%global __brp_strip_static_archive %{nil}
%global __brp_strip_comment_note %{nil}
%global __brp_python_bytecompile %{nil}
%global __brp_mangle_shebangs %{nil}
%global __brp_check_rpaths %{nil}

# Fast, multi-threaded payload compression so packaging the ~400 MB bundle takes
# seconds, not minutes (the default gzip -9 is single-threaded and slow).
%global _binary_payload w7T0.zstdio

# The package bundles a Python venv (with .dist-info) and Playwright's Chromium.
# Let rpm's automatic ELF scanner add the shared-library Requires (nss, gtk3,
# alsa-lib, … — always correct for the target), but DON'T let the Python
# dependency generator emit pythonXdist(...) Requires for the bundled venv (those
# packages live in our venv, not the distro). Also drop the auto-Requires for the
# PRIVATE bundled libraries that Chromium and Pillow carry with hash-suffixed
# sonames (e.g. libjpeg-31e2ca52.so…): they resolve via RPATH inside the package,
# so an external dependency on their versioned symbols is bogus and unsatisfiable.
# And strip any stray reference to the throwaway build path.
%global __requires_exclude ^(python[0-9.]*dist\\(|python\\(abi\\)|.*/dist/auto-keka|.*-[0-9a-f]{8}\\.so)

Name:           auto-keka
Version:        %{app_version}
Release:        1%{?dist}
Summary:        Keka auto attendance — clock in/out

License:        Proprietary
URL:            https://github.com/Quantum-vik/keka-automate
Source0:        %{name}-%{version}.tar.gz
Source1:        auto-keka-launcher.sh
Source2:        auto-keka.desktop
Source3:        auto-keka.png

# Ships compiled wheels (cryptography, pillow) and the Chromium binary, so this
# is an arch-specific package, not noarch.

# Runtime system packages the app loads via subprocess/dlopen (not detectable by
# the ELF scanner). dnf pulls these in at install time — installed once, never
# "every run".
Requires:       python3
Requires:       tesseract
Requires:       python3-tkinter
Requires:       python3-gobject
Requires:       gtk3
Requires:       webkit2gtk4.1
Requires:       zenity
Requires:       libnotify

%description
Auto-Keka automates Keka attendance (clock in / clock out) with a small desktop
panel. This package is self-contained: /opt/keka-automate ships its own Python
virtualenv (all pip dependencies) and Playwright's Chromium browser, and its
system dependencies are pulled in by dnf. The app runs with no first-run
downloads and no runtime setup. Ships with a built-in perpetual license.

%prep
%autosetup -n %{name}-%{version}

%build
# Everything (venv + Chromium) is built by build-rpm.sh before packaging.

%install
rm -rf %{buildroot}

# App source + bundled venv + bundled Chromium, read-only under /opt.
install -d %{buildroot}/opt/keka-automate
cp -a . %{buildroot}/opt/keka-automate/

# Launcher on PATH.
install -Dm0755 %{SOURCE1} %{buildroot}%{_bindir}/auto-keka

# Desktop entry + icon.
install -Dm0644 %{SOURCE2} %{buildroot}%{_datadir}/applications/auto-keka.desktop
install -Dm0644 %{SOURCE3} %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/auto-keka.png

%files
/opt/keka-automate
%{_bindir}/auto-keka
%{_datadir}/applications/auto-keka.desktop
%{_datadir}/icons/hicolor/256x256/apps/auto-keka.png

%post
update-desktop-database &>/dev/null || :
touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :

%postun
if [ $1 -eq 0 ] ; then
    touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :
    gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :
    update-desktop-database &>/dev/null || :
fi

%posttrans
gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :

%changelog
* Tue Sep 15 2026 Auto-Keka Packaging <noreply@anthropic.com> - %{app_version}-1
- Self-contained package: bundled venv + Chromium, system deps as Requires.
