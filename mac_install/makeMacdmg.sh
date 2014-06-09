SRCDIR=~/gcf
DESTDIR=~/omniTools/omniTools-2.6
COVERDIR=~/omniTools

cd ${SRCDIR}/src
py2applet --make-setup clear-passphrases.py 
python setup.py py2app --no-chdir
mv dist/clear-passphrases.app $DESTDIR
rm -r dist build setup.py 
py2applet --make-setup omni.py
python setup.py py2app --no-chdir
mv dist/omni.app $DESTDIR
rm -r dist build setup.py 
py2applet --make-setup omni-configure.py
python setup.py py2app --no-chdir
mv dist/omni-configure.app $DESTDIR
rm -r dist build setup.py 
py2applet --make-setup stitcher.py gcf/stitcher_logging.conf
python setup.py py2app --no-chdir
mv dist/stitcher.app $DESTDIR
rm -r dist build setup.py 
cd ../examples/
py2applet --make-setup readyToLogin.py
python setup.py py2app --no-chdir
mv dist/readyToLogin.app $DESTDIR
rm -r dist build setup.py 
py2applet --make-setup addMemberToSliceAndSlivers.py
python setup.py py2app --no-chdir
mv dist/addMemberToSliceAndSlivers.app $DESTDIR
rm -r dist build setup.py 
py2applet --make-setup remote-execute.py
python setup.py py2app --no-chdir
mv dist/remote-execute.app $DESTDIR
rm -r dist build setup.py

#copy License and make Applications link
ln -s /Applications $COVERDIR
cp ${SRCDIR}/windows_install/LICENSE.txt $COVERDIR
cp ${SRCDIR}/windows_install/LICENSE.txt $DESTDIR

#copy other files of interest
cp ${SRCDIR}/mac_install/background.png $DESTDIR
cp ${SRCDIR}/mac_install/addAliases.sh $DESTDIR
cp ${SRCDIR}/mac_install/INSTALL.txt $COVERDIR

#copy READMES
cp ${SRCDIR}/README-clearpassphrases.txt $DESTDIR
cp ${SRCDIR}/README-omni.txt $DESTDIR
cp ${SRCDIR}/README-omniconfigure.txt $DESTDIR
cp ${SRCDIR}/README-stitching.txt $DESTDIR
