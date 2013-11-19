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


# CGI script from extracting essential graphite graphs for a 
# specific host 

use warnings;
use strict;
use CGI qw/:standard/;
use LWP::UserAgent;
use JSON;
use Data::Dumper;
use URI::Escape;
my $graphite = 'http://grafitti-api.uio.no/';
my $query = new CGI;
my $width = 940;
my $from = "-1day";
my $until = "now";
my $format = "png";
my $height = 300;
my @graphs = qw( cpu_total mem_total interface_octets lv_bandwidth 
                 lv_throughput disk_bandwidth disk_throughput 
               );
my $host = $query->param("host");
$width = $query->param("width") if $query->param("width");
$height = $query->param("height") if $query->param("height");
$format = $query->param("format") if $query->param("format");
$from = $query->param("from") if $query->param("from");
$until = $query->param("until") if $query->param("until");
my $only_graph = $query->param("only_graph") if $query->param("only_graph");
@graphs = split(",",$query->param("graphs")) if $query->param("graphs");

my $g_host = $host;
$g_host =~ s/\./_/g;
my %graphs = ( 
             "cpu_total"         => \&graph_cpu_total,
             "mem_total"         => \&graph_mem_total,
             "interface_octets"  => \&graph_interface_octets,
             "lv_bandwidth"      => \&graph_lv_bandwidth,
             "disk_bandwidth"    => \&graph_disk_bandwidth,
             "lv_throughput"     => \&graph_lv_throughput,
             "disk_throughput"   => \&graph_disk_throughput,
             );

print_host_header();
print_uio_content_start() unless $only_graph;
if ( $g_host ) {
 do_graph();
 print_query_string();
} else {
list_hosts();
}
print_uio_content_end() unless $only_graph;

################ SUBS #############

sub list_hosts {
 my @hosts = get_metrics("collectd.*.cpu.0.user");
 @hosts = map { s/_uio_no.cpu.0.user//g ; $_ } @hosts;
 my @ghosts = map { s/collectd\.// ; $_ } @hosts;
 @hosts = map { s/_/\./g ; $_ } @hosts;
 my $num_cols = 6;
 my $c = 0;
 print "<table><tr>\n";
 foreach my $host( @hosts ) {
  print "<td><a href=\"http://app.uio.no/usit/bsd/collectd/cgi-bin/hostgraphs.cgi?host=$host.uio.no\">";
  print "$host</a></td>";
  $c++;
  if ( $c == $num_cols ) {
   print "</tr><tr>";
   $c = 0; 
  }
 }
 print "</tr></table>\n";
}

sub do_graph {
 foreach my $graph ( @graphs ) {
  &{$graphs{$graph}};
 }
}

sub graph_disk_bandwidth {
 my @disk_octets = get_metrics("collectd.$g_host.disk.{sd,cciss}*.octets.*");
 print_common_graph_element();
 print "vtitle=MB&
hideLegend=false&
title=Disk bandwidth&
";
 foreach my $metric ( @disk_octets ) {
  $metric =~ m/disk\.(.+?)\.octets\.(.+?)$/;
  print "target=alias\(scale\($metric,0.000001\),%22$1-$2%22\)&\n";
 }
 print '">';
}


sub graph_disk_throughput {
 my @metrics = get_metrics("collectd.$g_host.disk.{sd}*.ops.*");
 print_common_graph_element();
 print "vtitle=IOPS&
hideLegend=false&
title=Disk throughput&
";
 foreach my $metric (sort  @metrics ) {
  $metric =~ m/disk\.(.+?)\.ops\.(.+?)$/;
  print "target=alias\($metric,%22$1-$2%22\)&\n";
 }
 print '">';
}

sub graph_lv_bandwidth { 
 my @metrics = get_metrics("collectd.$g_host.disk.dm-*.octets.*");
 print_common_graph_element();
 print "vtitle=MB&
hideLegend=false&
title=Logical volume bandwidth&
";
 foreach my $metric ( sort @metrics ) {
  $metric =~ m/disk\.(dm-.+?)\.octets\.(.+?)$/;
  print "target=alias\(scale\($metric,0.000001\),%22$1-$2%22\)&\n";
 }
 print '">';

}

sub graph_lv_throughput { 
 my @metrics = get_metrics("collectd.$g_host.disk.dm-*.ops.*");
 print_common_graph_element();
 print "vtitle=IOPS&
hideLegend=false&
title=Logical volume throughput usage&
";
 foreach my $metric ( @metrics ) {
  $metric =~ m/disk\.(dm-.+?)\.ops\.(.+?)$/;
  print "target=alias\($metric,%22$1-$2%22\)&\n";
 }
 print '">';

}

sub graph_interface_octets {
 my @metrics = get_metrics("collectd.$g_host.interface.octets.*.*");
 print_common_graph_element();
 print "vtitle=Octets&
hideLegend=false&
title=Interface octets&
";
 foreach my $metric ( @metrics ) { 
  next if $metric =~ m/bond/;
  next if $metric =~ m/lo/;
  $metric =~ m/interface\.octets\.(.+?)\.(.+?)$/;
  print "target=alias\($metric,%22$1-$2%22\)&\n";
 } 
 print '">';
}

sub graph_cpu_total {
 print_common_graph_element();
 print "vtitle=jiffies&
title=Total CPU utilization&
areaMode=stacked&
target=alias\(sumSeries\(collectd.$g_host.cpu.*.user\),%22User%22\)&
target=alias\(sumSeries\(collectd.$g_host.cpu.*.wait\),%22Iowait%22\)&
target=alias\(sumSeries\(collectd.$g_host.cpu.*.system\),%22System%22\)&
target=alias\(sumSeries\(collectd.$g_host.cpu.*.idle\),%22Idle%22\)&
\">";
}

sub graph_mem_total {
 print_common_graph_element();
 print "vtitle=MB&
title=Total Memory consumption&
areaMode=stacked&
target=alias\(collectd.$g_host.memory.cached,%22Cached%22\)&
target=alias\(collectd.$g_host.memory.buffered,%22Buffered%22\)&
target=alias\(collectd.$g_host.memory.used,%22Used%22\)&
target=alias\(collectd.$g_host.memory.free,%22Free%22\)&
\">";
}

sub print_common_graph_element {
 print "<img src=\"$graphite/render?
width=$width&
height=$height&
until=$until&
from=$from&
format=$format&";
}

sub print_host_header {
 print "Content-type: text/html; charset=UTF-8\n\n";
 # Page header
 print <<EOF;
 <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.
dtd">
 <html>
 <head>
 <meta http-equiv="content-type" content="text/html; charset=UTF-8">
 <title>$host</title>
 </head>
 <body>
EOF
}

sub print_query_string {
 print "<pre>\n";
 print "Query string: host=$host&from=$from&until=$until&height=$height&width=$width&format=$format&graphs="; 
 print join(",",@graphs);
 print "\n";
 print "Date format: hh:mm_YYYYMMDD\n";
 print "Add \"only_graph=1\" to exclude uio-header & footer \n";
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
 my $appname;
 my $tagline;
 if ( $host ) {
  $appname = $host;
  $tagline = "Grafer for: $host";
 } else {
  $appname = "Hostgrafer";
  $appname = "Liste over maskiner med grafer i graphite";
 }
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
       <a href=\'/usit/bsd/collectd/cgi-bin/hostgraphs.cgi\'>Hostgrafer</a>
       <span id="tagline">$tagline
</span>
    </div>
  </div>
</div>
<!-- Page header end -->

<!-- Page content starts -->
<div id="app-content">


<div id="app-content"><div id="app-name">
}
}
