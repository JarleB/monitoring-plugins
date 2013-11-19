#!/usr/bin/perl 

# Author: Jarle Bjørgeengen <jarle.bjorgeengen@usit.uio.no>


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

# Author: Jarle Bjørgeengen <jarle.bjorgeengen@usit.uio.no>

# Script for pulling performance data from snmp on admin-evs
# and export to graphite.
# Running on hds-mgmt02.uio.no 

use warnings;
use strict; 
use SNMP::Simple;
use Getopt::Long;
use Data::Dumper;
use IO::Socket;

my $admin_evs;
my $community;
my $carbon_port;
my $carbon_host;
my $debug;
my $graphite_prefix = 'hds.hnas';

my $time = time();

GetOptions("admin-evs=s"     => \$admin_evs,
           "community=s"     => \$community,
           "carbon-host=s"   => \$carbon_host,
           "carbon-port=s"   => \$carbon_port,
           "debug"           => \$debug,
    );
unless ( $admin_evs && $community && $carbon_host && $carbon_port) {
 usage();
}

# Load the hnas mib. Files must be in default mib dir for the system.
&SNMP::loadModules('BLUEARC-SERVER-MIB');

my $carbon_socket = IO::Socket::INET->new(Proto     => "tcp",
                                            PeerAddr  => $carbon_host,
                                            PeerPort  => $carbon_port)
        or die "can't connect to port $carbon_port on $carbon_host: $!";

$carbon_socket->autoflush(1);


my $s = new SNMP::Simple(DestHost => $admin_evs, Community => $community , Version => 2,Timeout => 20000000);

#BLUEARC-SERVER-MIB::clusterPNodeTable
my @clusterpnodetable = $s->get_table('clusterPNodeId','clusterPNodeName','clusterPNodeStatus');

# Store node names indexed by node ID
my %nodenames;
my %fslabels;

foreach my $n (@clusterpnodetable) {
 $nodenames{$n->[0]} = $n->[1];
}


# BLUEARC-SERVER-MIB::cpuUtilizationTable
$time = time();
my @cpuutilizationtable = $s->get_table('cpuUtilizationCnIndex','cpuIndex','cpuUtilization');

foreach (@cpuutilizationtable) {
  my ($pnode,$cpuindex,$util) = ($nodenames{$_->[0]},$_->[1],$_->[2]);
  my $ret = tx_carbon("$graphite_prefix.pnode.$pnode.cpuutil.$cpuindex",$util);
#  print "$ret: $pnode,$cpuindex,$util\n" if $debug;
}

# BLUEARC-SERVER-MIB::fpgaUtilizationTable
$time = time();
my @fpgautilizationtable = $s->get_table('fpgaUtilizationCnIndex','fpgaUtilizationFpgaIndex','fpgaUtilizationFpgaName','fpgaUtilization');

foreach (@fpgautilizationtable) {
  my ($pnode,$fpganame,$util) = ($nodenames{$_->[0]},$_->[2],$_->[3]);
  my $ret = tx_carbon("$graphite_prefix.pnode.$pnode.fpgautil.$fpganame",$util);
#  print "$ret: $pnode,$cpuindex,$util\n" if $debug;
}

# BLUEARC-SERVER-MIB::metaDataCacheStatsTable
$time = time();
my @metadatacachetable = $s->get_table('metaDataCacheStatsFsId','metaDataCache','metaDataCacheStatsFsLabel','metaDataCacheStatsHits','metaDataCacheStatsMisses','metaDataCacheStatsFsId');

foreach (@metadatacachetable) {
  my ($fslabel,$metadatacache,$hit,$miss,$fsid) = ($_->[2],$_->[1],$_->[3],$_->[4],$_->[5]);
  my $ret = tx_carbon("$graphite_prefix.fs.$fslabel.metadatacache.$metadatacache.hit",$hit);
  $ret = tx_carbon("$graphite_prefix.fs.$fslabel.metadatacache.$metadatacache.miss",$miss);
  $fslabels{$fsid} = $fslabel;
}


# BLUEARC-SERVER-MIB::sectorCacheStatsTable
$time = time();
my @sectorcachetable = $s->get_table('sectorCacheStatsCnIndex','sectorCacheType','sectorCacheStatsHitsPSI','sectorCacheStatsHitsSSI','sectorCacheStatsMissesPSI','sectorCacheStatsMissesSSI');

foreach (@sectorcachetable) {
  my ($pnode,$type,$hit_psi,$hit_ssi,$miss_psi,$miss_ssi) = ($nodenames{$_->[0]},$_->[1],$_->[2],$_->[3],$_->[4],$_->[5]);
  my $ret = tx_carbon("$graphite_prefix.pnode.$pnode.sectorcache.$type.psi.hit",$hit_psi);
  $ret    = tx_carbon("$graphite_prefix.pnode.$pnode.sectorcache.$type.ssi.hit",$hit_ssi);
  $ret    = tx_carbon("$graphite_prefix.pnode.$pnode.sectorcache.$type.psi.miss",$miss_psi);
  $ret    = tx_carbon("$graphite_prefix.pnode.$pnode.sectorcache.$type.ssi.miss",$miss_ssi);
}


# BLUEARC-SERVER-MIB::protocolStatsTable
$time = time();
my @protocolstatstable = $s->get_table('protStatsFsLabel','protStatsFlavor','protStatsOpCodeName','protOpCount','protCumulativeLatency');

foreach (@protocolstatstable) {
  my ($fslabel,$flavor,$op_name,$op_count,$cum_lat) = ($_->[0],$_->[1],$_->[2],$_->[3],$_->[4]);
  my $ret = tx_carbon("$graphite_prefix.fs.$fslabel.ops.$flavor.$op_name",$op_count) if $op_count > 0;
  $ret    = tx_carbon("$graphite_prefix.fs.$fslabel.cum_lat.$flavor.$op_name",$cum_lat) if $cum_lat > 0;
}

# BLUEARC-SERVER-MIB::protocolXferStatsTable
$time = time();
my @protocolxferstatstable = $s->get_table('protocolXferStatsFsLabel','protocolXferStatsFlavor','protocolXferStatsBytesRead','protocolXferStatsBytesWritten');

foreach (@protocolxferstatstable) {
  my ($fslabel,$flavor,$bytes_read,$bytes_written) = ($_->[0],$_->[1],$_->[2],$_->[3]);
  my $ret = tx_carbon("$graphite_prefix.fs.$fslabel.xfer.$flavor.read",$bytes_read) if $bytes_read > 0;
  $ret    = tx_carbon("$graphite_prefix.fs.$fslabel.xfer.$flavor.write",$bytes_written) if $bytes_written > 0;
}

# BLUEARC-SERVER-MIB::intraClusterPortErrorTable
$time = time();
my @intraclusterporterrortable = $s->get_table('intraClusterPortErrsCnId','mirroringRetransmits','cnsRetransmits');

foreach (@intraclusterporterrortable) {
  my ($pnode,$mirror_retransmits,$cns_retransmits) = ($nodenames{$_->[0]},$_->[1],$_->[2]);
  my $ret = tx_carbon("$graphite_prefix.pnode.$pnode.cluster_port_errors.mirror", $mirror_retransmits);
  $ret    = tx_carbon("$graphite_prefix.pnode.$pnode.cluster_port_errors.cns", $cns_retransmits);
}

# BLUEARC-SERVER-MIB::fsStatsTable
$time = time();
my @fsstatstable = $s->get_table('fsLabel','opsPerSecAverage');

foreach (@fsstatstable) {
  my ($fslabel,$ops) = ($_->[0],$_->[1]);
  my $ret = tx_carbon("$graphite_prefix.fs.$fslabel.ops_pr_sec_avg.fs", $ops);
}

# BLUEARC-SERVER-MIB::fcStatisticsTable
$time = time();
my @fcstatstable = $s->get_table('fcStatsClusterNode','fcStatsInterfaceIndex','fcStatsTotalRxBytes','fcStatsTotalTxBytes');

foreach (@fcstatstable) {
  my ($pnode,$if_index,$rx_bytes,$tx_bytes) = ($nodenames{$_->[0]},$_->[1],$_->[2],$_->[3]);
  my $ret = tx_carbon("$graphite_prefix.pnode.$pnode.interfaces.fc.$if_index.rx_bytes",$rx_bytes);
  $ret    = tx_carbon("$graphite_prefix.pnode.$pnode.interfaces.fc.$if_index.tx_bytes",$tx_bytes);
}

# BLUEARC-SERVER-MIB::nvramFsStatsTable
$time = time();
my @nvramfsstatstable = $s->get_table('fsId','nvramFsStatsWaitedAllocs','nvramFsStatsWaitingAllocs');

foreach (@nvramfsstatstable) {
  my ($fsid,$waited_allocs,$waiting_allocs) = ($_->[0],$_->[1],$_->[2]);
  my $ret = tx_carbon("$graphite_prefix.fsbyid.$fsid.nvram.waited_allocs",$waited_allocs);
  $ret    = tx_carbon("$graphite_prefix.fsbyid.$fsid.nvram.waiting_allocs",$waiting_allocs);
}

# Disabled 2013-08-31, since it produces rubish
# Counter turning over more than once during an interval ? 
#
# IF-MIB::ifTable
#my @iftable = $s->get_table('ifIndex','ifDescr','ifInOctets','ifOutOctets','ifInUcastPkts','ifOutUcastPkts');

#foreach (@iftable) {
# my ($if_index,$if_descr,$if_in_octets,$if_out_octets,$if_in_ucastpkts,$if_out_ucastpkts) = ($_->[0],$_->[1],$_->[2],$_->[3],$_->[4],$_->[5]);
# $if_descr =~ m/interface\s+?(.+?)\s+?on Cluster Node (\d+?)/;
# my $ifname = $1;
# my $pnode = $nodenames{$2};
# if ( $ifname =~ /ag/ ) {
#   my $ret = tx_carbon("$graphite_prefix.pnode.$pnode.interfaces.ethernet.$ifname.in_octets",$if_in_octets);
#   $ret = tx_carbon("$graphite_prefix.pnode.$pnode.interfaces.ethernet.$ifname.out_octets",$if_out_octets);
#   $ret = tx_carbon("$graphite_prefix.pnode.$pnode.interfaces.ethernet.$ifname.in_pkts",$if_in_ucastpkts);
#   $ret = tx_carbon("$graphite_prefix.pnode.$pnode.interfaces.ethernet.$ifname.out_pkts",$if_out_ucastpkts);
# }
#}

#print Dumper(@cpuutilzationtable);
close($carbon_socket);

sub usage {
  print "Usage: $0 --admin-evs <fqdn or ip of admin-evs> \\ 
--community <snmp community string> \\
--carbon-host <fqdn or ip of carbon host> \\
--carbon-port <listening port of carbon>
\n";
  exit 1;
}

sub tx_carbon {
  my $m = shift; # Metric name
  my $v = shift; # Value
  return "Malformed metric name" if $m !~ /\w\.\w/;
  return "Malformed value" if $v !~ /\d\.*?\d*?/;
  print $carbon_socket "$m $v $time\n" unless $debug;
  print "$m $v $time\n" if $debug;
}
