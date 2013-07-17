#!/usr/bin/perl 

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


use warnings;
use strict;
use Data::Dumper;
use Collectd::Unixsock ();


#my @hosts = 'http://10.33.100.1/';
die "No hosts given as argument for query" unless $ARGV[0];
my @devices = @ARGV;

foreach my $device ( @devices ) {
  my $device_data = ();
  my $num_ports = get_num_ports($device);
  die "Bad number of ports" unless $num_ports =~ m/\d+/;
  to_collectd($device,'total'); 
  for ( my $c = 1; $c <= $num_ports ; $c++ ) {
   to_collectd($device,$c);
  }  
}
#my $total_kwh = get_totals(); 
#my $foo = get_port(2);
##print Dumper($foo);
#print get_page($host,"PageMensaStatus.htm");

###### SUBS ###############

sub to_collectd {
 my $unixsock = "/var/run/collectd-unixsock";
 my $host = shift;
 my $time = time();
 my $port = shift;
 my $portname;
 my $id_host = `/bin/hostname` ;
 chomp($id_host);
 $id_host .= "-$host";
 my $d;
 if ( $port =~ /\d+/ ) {
  $d = get_port_data($host,$port);
 } elsif ($port eq "total" ) {
  $d = get_total_energy($host);
 }
 my @portnames =  ( keys %{$d} ) ;
 die "Only one port at the time" unless ( $#portnames == 0 ) ;
 $portname = $portnames[0];
 print Dumper($d);
 my $s = Collectd::Unixsock->new($unixsock) or die "Cannot open socket $unixsock: $!\n";
 my %identifier = (
                   'host' => $id_host,
                   'interval' => 60,
                   'type' => 'energy',
                   'plugin' => 'ibm-dpi',
                   'type_instance' => $portname,
                  );
 $s->putval(%identifier, time=> $time, values => [ $d->{$portname}->{'cum_kwh'} ]);
 %identifier = (
                   'host' => $id_host,
                   'interval' => 60,
                   'type' => 'power',
                   'plugin' => 'ibm-dpi',
                   'type_instance' => $portname,
                  );
 $s->putval(%identifier, time=> $time, values => [ $d->{$portname}->{'power'} ]);
 $s->destroy ();
}

sub get_num_ports {
 my $host = shift;
 my $page = get_page($host,"PageMensaStatus.htm");
 $page =~ m/var\s+ElementOuletName\s+=\s+new\s+Array\((.*?)\)/sg;
 my $js_array = $1; 
 $js_array =~s/\n//sg;
 $js_array =~s/\"//sg;
 my @a = split(",",$js_array);
 return $#a + 1;
} 
 
sub get_port_data {
 my $ret;
 my $host = shift;
 my $portnum = shift;
 my $portnum_page = get_page($host,"PageStatisticsJ$portnum.htm");
 $portnum_page =~ m/var\s+Elementstatus\s+=\s+new\s+Array\((.*?)\)/sg;
 my $js_array = $1;
 $js_array =~s/\n//sg;
 $js_array =~s/\"//sg;
 my @a = split(",",$js_array);
 my ($outlet_name,$outlet_shortdesc) = split(":",$a[0]);
 #print join(",",@a)."\n";
 $ret->{$outlet_name}->{'cum_kwh'} = $a[15];
 $ret->{$outlet_name}->{'power'} = $a[12];
 $ret->{$outlet_name}->{'outlet_shortdesc'} = $outlet_shortdesc;
 return $ret;
}

sub get_total_energy {
  my $host = shift;
  my $ret;
  my $totals_page = get_page($host,'PageStatistics.htm');
  $totals_page =~ m/CumWattHours\s+=\s+\"(\d+)\"/;
  my $cum_kwh = $1;
  $totals_page =~ m/var\s+Elementstatus\s+=\s+new\s+Array\((.*?)\)/sg;
  my $js_array = $1;
  $js_array =~s/\n//sg;
  $js_array =~s/\"//sg;
  my @a = split(",",$js_array);
  $ret->{'total'}->{'cum_kwh'} = $cum_kwh;
  $ret->{'total'}->{'power'} = $a[31];
  print $totals_page;
  return $ret; 
} 

sub get_page {
  my $host = shift;
  my $page = shift;
  my $cmd = "/usr/bin/curl --silent --user monitor:`cat pw`  $host/";
  my $ret  = `$cmd$page`;
}

