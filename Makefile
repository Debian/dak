sql-aptvc.so: sql-aptvc.cpp
	gcc -Wall -I/usr/include/postgresql/ sql-aptvc.cpp -fPIC -shared -lapt-pkg -o sql-aptvc.so

clean: 
	rm -f sql-aptvc.so
