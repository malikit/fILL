#!/usr/bin/perl

use CGI;
use DBI;
use JSON;

my $query = new CGI;
my $lid = $query->param('lid');

# sql to get new (not yet handled) patron requests
my $SQL = "select 
  pr.prid, 
  date_trunc('second',pr.ts) as ts, 
  p.name, 
  p.card, 
  pr.title, 
  pr.author,
  pr.medium,
  pr.pubdate,
  pr.isbn,
  p.is_verified
from 
  patron_request pr 
  left join patrons p on p.pid = pr.pid 
where 
  pr.lid = ? 
order by 
  name, ts";

my $dbh = DBI->connect("dbi:Pg:database=maplin;host=localhost;port=5432",
                       "mapapp",
                       "maplin3db",
                       {AutoCommit => 1, 
                        RaiseError => 1, 
                        PrintError => 0,
                       }
    ) or die $DBI::errstr;

$dbh->do("SET TIMEZONE='America/Winnipeg'");

my $aref = $dbh->selectall_arrayref($SQL, { Slice => {} }, $lid );

# any of them local?
my $localcopy_href = $dbh->selectall_hashref("select prid from patron_request_sources where lid=?", 'prid', undef, $lid);

foreach my $href (@$aref) {
    if (exists $localcopy_href->{ $href->{prid} }) {
	$href->{"has_local_copy"} = 1;
    } else {
	$href->{"has_local_copy"} = 0;
    }
}

$dbh->disconnect;

print "Content-Type:application/json\n\n" . to_json( { new_patron_requests => $aref } );
