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

# CGI script for extracting essential hnas graphs.
# from graphite.

use warnings;
use strict;
use CGI qw/:standard/;
use LWP::UserAgent;
use JSON;
use IO::Socket::INET;
use Data::Dumper;
use URI::Escape;
my $hnas_inventory_port = '5858';
my $hnas_inventory_host = 'grafitti.uio.no';
my $graphite = 'http://collectd-prod02.uio.no/';
my $query = new CGI;
my $width = 940;
my $from = "-1day";
my $until = "now";
my $format = "png";
my $height = 300;
my @pnode_cpus = get_metrics("hds.hnas.pnode.hnas-*.cpuutil.*");
my @filesystem_fsa_hits = get_metrics("hds.hnas.fs.*.metadatacache.fsa.hit");
my @filesystem_waited_allocs;
my @fsnames;

# Get inventory information from hnas-inventory service
# https://www.usit.uio.no/om/tjenestegrupper/storage/tjenester/hitachi/hnas-drift.html#inventory
# Aggregated graphs over physical nodes depend on this.
#
my $hnas_inventory_socket = IO::Socket::INET->new(
   Proto     => "tcp",
   PeerAddr  => $hnas_inventory_host,
   PeerPort  => $hnas_inventory_port) 
   or die "can't connect to port $hnas_inventory_port on $hnas_inventory_host $!";
my $hnas_inventory_json;
while(<$hnas_inventory_socket>) {
  $hnas_inventory_json .= $_;
}
close($hnas_inventory_socket);

# Rearrange inventory to fit the needs for information lookup.
#
my $hnas_inventory_data = decode_json($hnas_inventory_json);
my %fs_labels;
my %evs_ids;
my $pnode_fses;
my $pnode_evses;
foreach my $evs_id (keys %{$hnas_inventory_data} ) {
  my $pnode_name = $hnas_inventory_data->{$evs_id}->{'pnode_name'};
  my $evs_name = $hnas_inventory_data->{$evs_id}->{'label'};
  # Hash for looking up evs ID by name
  $evs_ids{$evs_name} = $evs_id;
  # Arrays of EVS'es per physical node
  push(@{$pnode_evses->{$pnode_name}},$evs_name);
  foreach my $fs_name (keys %{$hnas_inventory_data->{$evs_id}->{'fs'}}) {
    # Hash for looking up EVS names by id
    $fs_labels{$hnas_inventory_data->{$evs_id}->{'fs'}->{$fs_name}} = $fs_name;
    # Array of filesystem names per physicale node
    push(@{$pnode_fses->{$pnode_name}},$fs_name);
  } 
}

# Build array of filsystem names from querying a metrics that most 
# likeliy exist for all filesystems.
# (Created before hnas inventory service existed) 
#
foreach (@filesystem_fsa_hits) {
   m/hnas\.fs.(.+?)\.metadatacache/;
   my $fsname = $1;
   push(@fsnames,$fsname);
}

# Graph descriptions
my %available_graphs = (   pnode_cpu_util           => 'Physical node CPU utilization',
                           pnode_fpga_util          => 'Physical node FPGA utilization',
                           sector_cache_hit_rates   => 'Physical node sector cache hit rates',
#                           fs_nvram                 => 'File system NVRAM waite[d|ing] allocations',
                           fs_latency               => 'File system protocol access latency',
                           fs_ops                   => 'File system protocol operations',
                           fs_ops_aggregated        => 'File system protocol operations aggregated over physical node by EVS name',
                           fs_bytes                 => 'File system protocol bandwidth consumption',
                           fs_bytes_aggregated      => 'File system protocol bandwidth consumption aggregated over physical node by EVS name',
                           fs_metadatacache         => 'File system metadata cache hit rates',
                           pnode_fc_interfaces      => 'Fibre channel interfaces',
                         );

my $target_prefix = 'hds.hnas.';

# store URL-parameters
$format = $query->param("format") if $query->param("format");
$width = $query->param("width") if $query->param("width");
$height = $query->param("height") if $query->param("height");
$from = $query->param("from") if $query->param("from");
$until = $query->param("until") if $query->param("until");
my $only_graph = $query->param("only_graph") if $query->param("only_graph");
my @graphs = split(",",$query->param("graphs")) if $query->param("graphs");

# «Links» to functions
my %graphs = ( 
             "pnode_cpu_util"         => \&graph_pnode_cpu_util,
             "pnode_fpga_util"        => \&graph_pnode_fpga_util,
             "pnode_aggr_bw"          => \&graph_pnode_aggr_bw,
             "sector_cache_hit_rates" => \&graph_sector_cache_hit_rates,
#             "fs_nvram"               => \&graph_fs_nvram,
             "fs_latency"             => \&graph_fs_latency,
             "fs_ops"                 => \&graph_fs_ops,
             "fs_ops_aggregated"      => \&graph_fs_ops_aggregated,
             "fs_bytes"               => \&graph_fs_bytes,
             "fs_bytes_aggregated"    => \&graph_fs_bytes_aggregated,
             "fs_metadatacache"       => \&graph_fs_metadatacache,
             "pnode_fc_interfaces"    => \&graph_pnode_fc_interfaces,
             );

print_header();
print_uio_content_start() unless $only_graph;
# Print list of available graphs if no graph parameter was given
if ( $query->param("graphs") ) {
 print_query_string();
 do_graph();
} else {
 print "<ul>\n";
 foreach my $g (keys %available_graphs) {
  print '<li><a href="'.$query->self_url."?graphs=$g&only_graph=true\">$available_graphs{$g}</a>\n"
 }
 print "</ul>\n";
}

print_uio_content_end() unless $only_graph;

################ SUBS #############

sub graph_pnode_fc_interfaces {
   my $prefix = 'hds.hnas.pnode';
   # Indirect way of looping over physical nodes, assuming only one CPU pr host
   foreach my $trgt ( @pnode_cpus ) {
     $trgt =~ m/pnode\.(hnas-.+?)\./;
     my $pnode = $1;
     print_common_graph_element();
     print "vtitle=Bytes&
title=FC interface bandwidth usage for $pnode&
yMax=400000000&
yMin=-400000000&
";
     my @pnode_fc_metrics = get_metrics("$prefix.$pnode.interfaces.fc.*.*");
     foreach my $m (@pnode_fc_metrics) {
       if ( $m =~ m/rx_bytes/) {
         print "target=substr(scaleToSeconds(nonNegativeDerivative($m),1),6,8)&\n";
       } elsif ( $m =~ m/tx_bytes/ ) {
         # Flip TX bytes down by scaling with -1
         print "target=substr(scale(scaleToSeconds(nonNegativeDerivative($m),1),-1),6,8)&\n";
       }
     }
     print '">';
   }
}

sub graph_pnode_cpu_util {
   print_common_graph_element();
   print "vtitle=%&
title=HNAS physical node CPU Utilization&
yMax=100&
yMin=0&
";
   # CPU util direct based on queried metrics stored in @pnode_cpus
   foreach my $trgt ( @pnode_cpus ) {
     $trgt =~ m/pnode\.(hnas-.+?)\./;
     my $alias = $1;
     print "target=alias\($trgt,%22$alias%22\)&";
   }
   print '">';
}

sub graph_fs_metadatacache {
  my $target_prefix = $target_prefix.'fs';
  my @caches = qw( fsa objIndirectionObject objLeaf objRoot wdir wfile wtree );
  foreach my $fsname (@fsnames) {
   # One graph per fs
   print_common_graph_element();
   print "vtitle=%&
title=$fsname, metadata cache hit rates&
yMin=0&
yMax=100&
";
   foreach my $cache ( @caches ) {
     # One line pr cache in each graph
     print "target=alias(scale(divideSeries(nonNegativeDerivative(hds.hnas.fs.$fsname.metadatacache.$cache.hit),sumSeries(derivative(hds.hnas.fs.$fsname.metadatacache.$cache.miss),nonNegativeDerivative(hds.hnas.fs.$fsname.metadatacache.$cache.hit))),100),'$cache')&\n";
   }
  print '">';
  }
}

sub graph_fs_latency {
  my $target_prefix = $target_prefix.'fs';
  foreach my $fsname (@fsnames) {
   # One graph per fs
   print_common_graph_element();
   print "vtitle=ms&
title=$fsname, Protocol access times&
yMin=0&
yMax=50&
hideLegend=false&
";
   # Pick responstimes of typical often operations with small data amount
   # counter is cumulative time in milliseconds. Need to derive, scale to seconds
   # and divide by 1000 (scale with 0.001) 
   print "target=substr(scale(scaleToSeconds(nonNegativeDerivative(hds.hnas.fs.$fsname.cum_lat.NFS.NFS3_ACCESS),1),0.001),6,7)&\n" ;
   print "target=substr(scale(scaleToSeconds(nonNegativeDerivative(hds.hnas.fs.$fsname.cum_lat.CIFS.CIFS1_QUERY_INFORMATION),1),0.001),6,7)&\n" ;
   print "target=substr(scale(scaleToSeconds(nonNegativeDerivative(hds.hnas.fs.$fsname.cum_lat.CIFS.CIFS2_QUERY_INFO),1),0.001),6,7)&\n" ;
   print '">';
  }
 
}

sub graph_fs_ops_aggregated_ {
  my $target_prefix = $target_prefix.'fs';
  foreach my $pnode_name ( sort keys %{$pnode_fses} ) {
    print_common_graph_element();
    print "vtitle=Operations/s&
title=$pnode_name, protocol operations&
areaMode=stacked&
hideLegend=false&
";
    foreach my $fs_name ( @{$pnode_fses->{$pnode_name}} ) {
      print "target=substr(scaleToSeconds(nonNegativeDerivative(sumSeries($target_prefix.$fs_name.ops.*.*)),1),3,5)&\n";
#      print "target=substr(scaleToSeconds(nonNegativeDerivative(sumSeries($target_prefix.$fs_name.ops.NFS.*)),1),3,6)&\n";
    } 
   print '">';
  }
}

sub graph_fs_ops_aggregated {
  my $target_prefix = $target_prefix.'fs';
  foreach my $pnode_name ( sort keys %{$pnode_fses} ) {
    # one graph pr pnode
    print_common_graph_element();
    print "vtitle=Operations/s&
title=$pnode_name, protocol operations&
areaMode=stacked&
hideLegend=false&
";
    foreach my $evs_name ( @{$pnode_evses->{$pnode_name}} ) {
    # All fs'es on a node in one graph is too busy, therefore aggregate all operations by evs'es 
    # for overview of EVS' total operation contribution on physical node.
    # If you really want that, use the graph_fs_ops_aggregated_ above (inactive)
      my $fs_list = join(",",keys %{$hnas_inventory_data->{$evs_ids{$evs_name}}->{'fs'}});
      print "target=alias(scaleToSeconds(nonNegativeDerivative(sumSeries($target_prefix.{$fs_list}.ops.*.*)),1),'$evs_name')&\n";
#      print "target=substr(scaleToSeconds(nonNegativeDerivative(sumSeries($target_prefix.$fs_name.ops.NFS.*)),1),3,6)&\n";
    } 
   print '">';
  }
}

sub graph_fs_ops {
  my $target_prefix = $target_prefix.'fs';
  foreach my $fsname (@fsnames) {
   # One graph per fs
   print_common_graph_element();
   print "vtitle=Operations/s&
title=$fsname, Protocol operations&
yMin=0&
yMax=15000&
";
   # Stack NFS and CIFS operations to see total operation and protocol-type contribution.
   print "target=alias(stacked(scaleToSeconds(nonNegativeDerivative(sumSeries(hds.hnas.fs.$fsname.ops.CIFS.*)),1)),'CIFS')&\n";
   print "target=alias(stacked(scaleToSeconds(nonNegativeDerivative(sumSeries(hds.hnas.fs.$fsname.ops.NFS.*)),1)),'NFS'))&\n";
   # Overlay WFS2 operations to see that how protocol operations convert to WFS2 operations underneath.
   # For some reason this metric is not of type counter....
   print "target=alias(hds.hnas.fs.$fsname.ops_pr_sec_avg.fs,'WFS2 operations'))&\n";
   print '">';
  }
}

sub graph_fs_bytes {
  my $target_prefix = $target_prefix.'fs';
  foreach my $fsname (@fsnames) {
   # One graph per fs
   print_common_graph_element();
   print "vtitleRight=Bytes/s&
title=$fsname, Protocol bytes&
areaMode=stacked&
yMin=0&
";
   print "target=substr(scaleToSeconds(nonNegativeDerivative(hds.hnas.fs.$fsname.xfer.*.*),1),5,7)&\n";
   print '">';
  }
}

sub graph_fs_bytes_aggregated {
  # Same concept as graph_fs_ops_aggregated
  my $target_prefix = $target_prefix.'fs';
  foreach my $pnode_name ( sort keys %{$pnode_fses} ) {
    print_common_graph_element();
    print "vtitle=Bytes/s&
title=$pnode_name, bytes/s&
areaMode=stacked&
hideLegend=false&
";
    foreach my $evs_name ( @{$pnode_evses->{$pnode_name}} ) {
      my $fs_list = join(",",keys %{$hnas_inventory_data->{$evs_ids{$evs_name}}->{'fs'}});
      print "target=alias(scaleToSeconds(nonNegativeDerivative(sumSeries($target_prefix.{$fs_list}.xfer.*.*)),1),'$evs_name')&\n";
    } 
   print '">';
  }
}

sub graph_fs_nvram {
  # Not active. Need to implement lookup of name by fsid
  my $target_prefix = $target_prefix.'fs';
  foreach (@filesystem_waited_allocs) {
   m/hnas\.fs.(.+?)\.nvram/;
   my $fsname = $1;
   print_common_graph_element();
   print "vtitle=Allocations/min&
title=$fsname, NVRAM waited/waiting allocation for filesystem&
yMin=0&
";
   print "target=alias(nonNegativeDerivative($target_prefix.$fsname.nvram.waited_allocs),'Waited')&\n";
   print "target=alias(nonNegativeDerivative($target_prefix.$fsname.nvram.waiting_allocs),'Waiting')&\n";
   print '">';
  }
}

sub graph_pnode_fpga_util {
   foreach (@pnode_cpus) {
     # Basically for each physical node... 
     m/pnode\.(hnas-.+?)\./;
     my $pnode = $1;
     print_common_graph_element();
     # Get util metrics for all FPGAs
     my @pnode_fpgas = get_metrics("hds.hnas.pnode.$pnode.fpgautil.*");
     print "vtitle=%&
title=$pnode physical node FPGA Utilization&
hideLegend=false&
yMax=100&
yMin=0&
";
     foreach my $trgt ( @pnode_fpgas ) {
       $trgt =~ m/pnode\.$pnode\.fpgautil\.(.+)/;
       # Grab the name of the fpga and use that as alias. (Was not aware of substr at this time)
       my $alias = "$1";
       print "target=alias\($trgt,%22$alias%22\)&";
     }
     print '">';
   }
}

sub graph_sector_cache_hit_rates {
  my @caches    = qw( read readAhead write ); 
  my @subcaches = qw( psi ssi ); 
  foreach (@pnode_cpus) {
     # One graph per physical node
     m/pnode\.(hnas-.+?)\./;
     my $pnode = $1;
     print_common_graph_element();
     print "vtitle=%&
title=$pnode sector cache hit rate&
hideLegend=false&
yMax=100&
yMin=0&
";
     foreach my $cache (@caches) {
       # All caches and subcaches in each graph
       foreach my $subcache (@subcaches) {
         print "target=alias(scale(divideSeries(nonNegativeDerivative(hds.hnas.pnode.$pnode.sectorcache.$cache.$subcache.hit),sumSeries(derivative(hds.hnas.pnode.$pnode.sectorcache.$cache.$subcache.miss),derivative(hds.hnas.pnode.$pnode.sectorcache.$cache.$subcache.hit))),100),'$cache-$subcache')&\n";
       }
     }     
   print '">';
  } 
}

# Funker ikke
# counter resets to often perhaps
# See also case HDS00184955 @ portal.hds.com
# which was closed without further notice.
#
sub graph_pnode_aggr_bw {
   foreach (@pnode_cpus) {
     m/pnode\.(hnas-.+?)\./;
     my $pnode = $1;
     print_common_graph_element();
     my @pnode_aggs = get_metrics("hds.hnas.pnode.$pnode.interfaces.ethernet.*.*octets");
     print "vtitle=Bit/s&
title=$pnode aggregate bandwidth usage&
hideLegend=false&
yMin=0&
";
     foreach my $trgt ( @pnode_aggs ) {
       $trgt =~ m/pnode\.$pnode\.interfaces\.ethernet\.(.+?)\.(.+)_octets/;
       my $alias = "$1-$2";
      #print "target=alias\(scale\(nonNegativeDerivative\($trgt\),8\),%22$alias%22\)&";
      #print "target=alias\(nonNegativeDerivative\($trgt\),%22$alias%22\)&";
      #print "target=alias\(nonNegativeDerivative\($trgt\),%22$alias%22\)&";
      print "target=alias\(scaleToSeconds\(nonNegativeDerivative\($trgt,8\)\),1\),%22$alias%22\)&";
     }
     print '">';
   }
}


sub do_graph {
 foreach my $graph ( @graphs ) {
  &{$graphs{$graph}};
 }
}


sub print_common_graph_element {
 print "<img src=\"$graphite/render?
width=$width&
height=$height&
until=$until&
from=$from&";
print "format=$format&" if $format;
}

sub print_header {
 print "Content-type: text/html; charset=UTF-8\n\n";
 # Page header
 print <<EOF;
 <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.
dtd">
 <html>
 <head>
 <meta http-equiv="content-type" content="text/html; charset=UTF-8">
 <title>Hitachi HNAS grafer</title>
 </head>
 <body>
EOF
}

sub print_query_string {
 print "<pre>\n";
 print "CGI-scriptet tar følgende parametere for manipulering av grafer:\n";
 print "------------------------------------------------------------------------------------------\n";
 print "Query string: from=$from&until=$until&height=$height&width=$width&format=$format&graphs="; 
 print join(",",@graphs);
 print "\n";
 print "Date format: hh:mm_YYYYMMDD\n";
 print "Add \"only_graph=1\" to exclude uio-header & footer \n";
 print "Image formats (format paramer) supported: svg,png\n";
 print "------------------------------------------------------------------------------------------\n";
 print "NB: Husk at du kan kopiere image-url for et enkelt bilde og justere alle tilgjengelige \n";
 print "Graphite-parametere selv. Se http://http://graphite.readthedocs.org/en/1.0/url-api.html \n";
 print "NB2: Grafer med «No Data» oppstår der hvor det ikke finnes data for objektet i Graphite\n";
 print "</pre>\n";
}

sub get_metrics {
 my $search_pattern = shift;
 my $ua = LWP::UserAgent->new;
 my $base_url = $graphite.'metrics/expand?query=';
 my $req = HTTP::Request->new(GET => $base_url.$search_pattern);
 my $res = $ua->request($req);
 my @ret;
  if ($res->is_success) {
  } else {
      print "Failed: ", $res->status_line, "\n";
  }
 my $json = $res->decoded_content;
 my $level = decode_json($json);
 foreach my $res ( @{$level->{'results'}} ) {
  if ( 
       $res !~ /\d{4}-/ &&
       $res !~ /emc-/ &&
       $res !~ /eva.*/
     ) {
    push(@ret,$res);
  }
 }
 return @ret;
}

sub print_uio_content_end {
print qq{</div>
<!-- Page content end -->

<!-- Page footer starts -->
<div id="app-footer-wrapper"> 
   <div id="app-footer">
     <div id="app-responsible">
       <span class="vrtx-label">Ansvarlig for denne tjenesten</span>
       <span><a href="http://www.usit.uio.no/sapp/bsd/">unix-drift - USIT</a></span>
     </div>
     <div id="contact-info">
       <div class="phone-fax-email">
         <span class="vrtx-label">Kontaktinformasjon</span>
         <span class="email">E-post: unix-drift\@usit.uio.no</span>
         <span class="tel">Telefon: 228 40004 (Houston)</span>
       </div>
     </div>
   </div>
</div>
<!-- Page footer end -->

<!-- UiO app JavaScript -->
<script type="text/javascript" src="../../mroles/uio-app.js"></script> 
</body>
</html>
}
}

sub print_uio_content_start {
 print qq{<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <!-- iPhone viewport -->
  <meta name="viewport" content="width=1020, user-scalable=yes" />

  <title>Host-grafer i graphite</title>

  <link href="../../mroles/uio-app-top-bottom.css" type="text/css" rel="stylesheet"/>
</head>
<body>

<!-- Page header starts -->
<div id="app-head-wrapper">
  <div id="line-top">
    <div id="uiologo">
      <a href="http://www.uio.no/">Universitetet i Oslo</a>
    </div>
  </div>
  <div id="app-head">
    <div id="app-name">
       <a href=\'/usit/bsd/collectd/cgi-bin/hnas-graphs.cgi\'>Hitachi HNAS grafer</a>
    </div>
  </div>
</div>
<!-- Page header end -->

<!-- Page content starts -->
<div id="app-content">


<div id="app-content"><div id="app-name">
}
}
