arch <- c("source", "all", "amd64", "i386", "alpha", "arm", "armel", "armhf", "hppa", "hurd-i386", "ia64",
	"kfreebsd-amd64", "kfreebsd-i386", "mips", "mipsel", "powerpc", "s390", "s390x", "sparc")
palette(c("midnightblue", "gold", "turquoise", "cyan", "black", "red", "OrangeRed", "green3", "blue", "magenta",
	"cornsilk3", "darkolivegreen3", "tomato4", "violetred2","thistle4", "steelblue2", "springgreen4",
	"salmon","gray"))
cname <- c("date",arch)
plotsize <- function(file,title,p,height=11.8,width=16.9) {
	bitmap(file=file,type="png16m",width=16.9,height=11.8)
	barplot(t(p),col = 1:19, main=title,
		xlab="date", ylab="size (MiB)")
	legend(par("usr")[1]+xinch(5),par("usr")[4]-yinch(0.1),legend=colnames(t),
		ncol=2,fill=1:19,xjust=1,yjust=1)
}
t <- (read.table("/srv/ftp-master.debian.org/misc/ftpstats.data",sep=",",header=0,row.names=1,col.names=cname))/1024/1024
v <- t[(length(t$all)-90):(length(t$all)),1:19]

#plotsize("/org/ftp.debian.org/web/size.png","Daily dinstall run size by arch",t)
plotsize("/srv/ftp.debian.org/web/size-quarter.png","Daily dinstall run size by arch (past quarter)",v)

