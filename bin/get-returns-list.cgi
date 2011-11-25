#!/usr/bin/perl

use CGI;
use DBI;
use JSON;

my $query = new CGI;
my $lid = $query->param('lid');

# sql to get items shipped to this library, which this library has not yet marked as received
my $SQL = "select r.id, r.title, r.author, ra.ts, ra.msg_to from request r left join requests_active ra on (r.id = ra.request_id) where ra.msg_from=? and ra.status='Received' and ra.request_id not in (select request_id from requests_active where msg_from=? and status='Returned') order by r.author, r.title";

my $dbh = DBI->connect("dbi:Pg:database=maplin;host=localhost;port=5432",
		       "mapapp",
		       "maplin3db",
		       {AutoCommit => 1, 
			RaiseError => 1, 
			PrintError => 0,
		       }
    ) or die $DBI::errstr;

my $aref = $dbh->selectall_arrayref($SQL, { Slice => {} }, $lid, $lid );
$dbh->disconnect;

print "Content-Type:application/json\n\n" . to_json( { returns => $aref } );
