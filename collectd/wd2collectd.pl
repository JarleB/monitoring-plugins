#!/usr/bin/perl
#
use warnings;
use strict;

use Collectd::Unixsock ();
use IO::Socket;
use Data::Dumper;

my $unixsock = "/var/run/collectd-unixsock";
my $time = time();
my %map = ( 
          'hum' => 'humidity',
          'temp' => 'temperature'
          );

my $ret = &wd2collectd("petterkopp.uio.no");

sub wd2collectd {
    my (@hosts)=@_;
    my $port = "5050";
    my $s = Collectd::Unixsock->new($unixsock) or die "Cannot open socket $unixsock: $!\n";
    foreach my $h (@hosts) {
        my $sock=IO::Socket::INET->new(PeerAddr => $h, PeerPort => $port);

        while(<$sock>) {
            unless (m/^(\S+) (\S+) (\S+)/) {
                next;
            }
        my %identifier = (
                         'host' => 'weatherducks',
                         'interval' => 300,
                         'type' => $map{$2},
                         'plugin' => 'wd',
                         'type_instance' => $1,
                      );
         #foreach my $r (keys %identifier) {
         # print "$r = -$identifier{$r}-\n";
         #}

         # print "$3\n"; 
         $s->putval(%identifier, time=> $time, values=> [ $3 ]);
      #      $ret{$1}{$2}=$3;
        }
        $sock->close();
    }
  $s->destroy ();
}



