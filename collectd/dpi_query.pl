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
use Getopt::Long;

my $hostname;
my $f_pw;
my $port;
my $nh;
my $pdata;

GetOptions("hostname=s"   => \$hostname,
           "pwfile=s"     => \$f_pw,
           "portnumber=s" => \$port,
           "nh"    => \$nh,
    );

unless ( $hostname && $f_pw ) {
 usage();
}


if ( ! $port ) {
  my $num_ports = get_num_ports($hostname);
  for ( my $c = 1; $c <= $num_ports ; $c++ ) {
    get_port_data($hostname,$c,$pdata);
  }
  unless ( $nh ) {
   print_heading();
  }
  print_data();
} elsif ( $port ){
  get_port_data($hostname,$port,$pdata);
  unless ( $nh ) {
   print_heading();
  }
  print_data();
}
#my @hosts = 'http://10.33.100.1/';
#my $total_kwh = get_totals(); 
#my $foo = get_port(2);
##print Dumper($foo);
#print get_page($host,"PageMensaStatus.htm");

###### SUBS ###############

sub print_data {
  foreach my $port ( sort { $a <=> $b } keys %{$pdata} ) {
    print "$port\;$pdata->{$port}->{'name'}\;";
    print "$pdata->{$port}->{'cum_kwh'}\;$pdata->{$port}->{'power'}\;";
    print "$pdata->{$port}->{'outlet_shortdesc'} \n";
  }
}

sub print_heading {
  print "Number;Name;Energy;Power;Short description\n";
}

sub usage {
 print "Usage: $0 --hostname <name-or-ip-of-device> --pwfile <file-with-pw-of-monitor-user\n";
 print "                      [--port <single-port-number>] [-nh]\n";
 exit 1;
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
 $pdata->{$portnum}->{'cum_kwh'} = $a[15];
 $pdata->{$portnum}->{'name'} = $outlet_name;
 $pdata->{$portnum}->{'power'} = $a[12];
 $pdata->{$portnum}->{'outlet_shortdesc'} = $outlet_shortdesc;
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
  my $cmd = "/usr/bin/curl --silent --user monitor:`cat $f_pw`  $host/";
  my $ret  = `$cmd$page`;
}

