#!/usr/bin/perl
#
# This needs to do error checking....
#
use strict;
use warnings;

use CGI;
use DBI;
use JSON;
use Switch;
use Data::Dumper;

my $query = new CGI;
my $cid = $query->param('cid');
my $override = $query->param('override');
my $data = $query->param('data');  # some overrides may require extra data; parsing is up to specific override

print STDERR "overriding cid [$cid], $override\n";

my $dbh = DBI->connect("dbi:Pg:database=maplin;host=localhost;port=5432",
		       "mapapp",
		       "maplin3db",
		       {AutoCommit => 1, 
			RaiseError => 1, 
			PrintError => 0,
		       }
    ) or die $DBI::errstr;

$dbh->do("SET TIMEZONE='America/Winnipeg'");

my $SQL = "select 
  ra.request_id, 
  ra.msg_from as borrower_id, 
  l.name as borrower, 
  ra.msg_to as lender_id, 
  l2.name as lender, 
  ra.status, 
  ra.message 
from 
  request_group g
  left join request_chain c on c.group_id = g.group_id
  left join request r on r.chain_id = c.chain_id
  left join requests_active ra on ra.request_id = r.id
  left join libraries l on (l.lid=ra.msg_from) 
  left join libraries l2 on (l2.lid=ra.msg_to) 
where 
  c.chain_id=?
  and status='ILL-Request' 
order by ra.ts";
my $aref = $dbh->selectall_arrayref($SQL, { Slice => {} }, $cid);
my $href = pop(@$aref);
print STDERR Dumper($href);
my $reqid = $href->{"request_id"};

$SQL = "insert into requests_active (request_id, msg_from, msg_to, status, message) values (?,?,?,?,?)";
my $borrower_id;
my $lender_id;
my $status = "Message";
my $message = "";
my $retval;
my $return_data_href;

switch( $override ) {

    case "bReceive" {
	# borrowing override
	$borrower_id = $href->{"borrower_id"};
	$lender_id = $href->{"lender_id"};
	# can only force 'Shipped' if the lender hasn't already marked it as 'Shipped'
	my $cntAnswers = $dbh->selectrow_array( "select count(*) from requests_active where request_id=? and msg_from=? and status like 'Shipped';", undef, $reqid, $lender_id );
	if ((defined $cntAnswers) && ($cntAnswers == 0)) {
	    $message = $href->{"borrower"} . " received item without " . $href->{"lender"} . " marking as 'Shipped'";
	    # borrower sends a message about overriding
	    $retval = $dbh->do( $SQL, undef, $reqid, $borrower_id, $lender_id, $status, $message );	
	    # force the ILL to be marked as Shipped by the lender
	    $retval = $dbh->do( $SQL, undef, $reqid, $lender_id, $borrower_id, 'Shipped', "override by $href->{borrower}" );
	    $return_data_href->{ success } = $retval;
	    $return_data_href->{ status } = "Shipped";
	    $return_data_href->{ message } = "override";
	} else {
	    $return_data_href->{ success } = 0;
	    $return_data_href->{ status } = "Could not force 'Shipped'";
	    $return_data_href->{ message } = "Lender has already shipped.";
	    $return_data_href->{ alert_text } = "Could not override this request,\nlender has already shipped.\nPlease check your Receiving list.";
	}
    }

    case "bCancel" {
	# borrowing override
	$borrower_id = $href->{"borrower_id"};
	$lender_id = $href->{"lender_id"};
	# can only cancel if the lender hasn't answered yet
	my $cntAnswers = $dbh->selectrow_array( "select count(*) from requests_active where request_id=? and msg_from=? and status like 'ILL-Answer%';", undef, $reqid, $lender_id );
	print STDERR "cntAnswers: $cntAnswers\n";
	if ((defined $cntAnswers) && ($cntAnswers == 0)) {
	    print STDERR "...so cancelling\n";
	    $message = $href->{"borrower"} . " cancelled the request to " . $href->{"lender"};
	    # borrower sends a message about overriding
	    $retval = $dbh->do( $SQL, undef, $reqid, $borrower_id, $lender_id, $status, $message );
	    # force the ILL to be marked as Cancelled by the lender
	    $retval = $dbh->do( $SQL, undef, $reqid, $lender_id, $borrower_id, 'Cancelled', "override by $href->{borrower}" );	
	    # ...and move to history
	    $retval = move_to_history( $dbh, $reqid );
	    $return_data_href->{ success } = $retval;
	    $return_data_href->{ status } = "Cancelled";
	    $return_data_href->{ message } = "override";
	} else {
	    print STDERR "...so NOT cancelling\n";
	    $return_data_href->{ success } = 0;
	    $return_data_href->{ status } = "Could not cancel";
	    $return_data_href->{ message } = "Lender has already answered.";
	    $return_data_href->{ alert_text } = "Could not cancel this request,\nlender has already answered.";
	}
    }

    case "bNoFurtherSources" {
	# borrowing override
	$borrower_id = $href->{"borrower_id"};
	$lender_id = $href->{"lender_id"};
	# can only move to history from here if there is a message saying "No further sources"
	my $cntAnswers = $dbh->selectrow_array( "select count(*) from requests_active where request_id=? and message='No further sources';", undef, $reqid);
	print STDERR "cntAnswers: $cntAnswers\n";
	if ((defined $cntAnswers) && ($cntAnswers == 1)) {
	    print STDERR "...so no further sources, moving to history\n";
	    $retval = move_to_history( $dbh, $reqid );
	    $return_data_href->{ success } = $retval;
	    $return_data_href->{ status } = "Moved to history";
	    $return_data_href->{ message } = "";
	} else {
	    print STDERR "...so NOT moving to history\n";
	    $return_data_href->{ success } = 0;
	    $return_data_href->{ status } = "Could not move to history";
	    $return_data_href->{ message } = "No 'No further sources' message.";
	    $return_data_href->{ alert_text } = "Could not move this request to history,\nno 'No further sources' message.";
	}
    }

    case "bTryNextLender" {
	# borrowing override
	$borrower_id = $href->{"borrower_id"};
	$lender_id = $href->{"lender_id"};
	# can only cancel if the lender hasn't answered yet
	my $cntAnswers = $dbh->selectrow_array( "select count(*) from requests_active where request_id=? and msg_from=? and status like 'ILL-Answer%';", undef, $reqid, $lender_id );
	if ((defined $cntAnswers) && ($cntAnswers == 0)) {
	    $message = $href->{"borrower"} . " is trying next lender";
	    # borrower sends a message about overriding
	    $retval = $dbh->do( $SQL, undef, $reqid, $borrower_id, $lender_id, $status, $message );
	    # mark the ILL as Cancelled by the borrower
	    $retval = $dbh->do( $SQL, undef, $reqid, $borrower_id, $lender_id, 'Cancelled', "override by $href->{borrower}" );	
	    # mark the cancellation as acknowleged by the lender (so the ILL does not show up on the lender's pull list / respond list)
	    $retval = $dbh->do( $SQL, undef, $reqid, $lender_id, $borrower_id, 'CancelReply|Ok', "override by $href->{borrower}" );	

	    # try next lender (from try-next-lender.cgi)
	    my @gcr = $dbh->selectrow_array("select g.group_id, c.chain_id, r.id from request r left join request_chain c on c.chain_id=r.chain_id left join request_group g on c.group_id=g.group_id where r.id=?", undef, $reqid);

	    $SQL = "select lid, sequence_number from sources where group_id=? and (tried is null or tried=false) order by sequence_number";
	    my @ary = $dbh->selectrow_array( $SQL, undef, $gcr[0] );

	    my $retval = 0;
	    if (@ary) {
		# message to requesting library
		$SQL = "insert into requests_active (request_id, msg_from, msg_to, status, message) values (?,?,?,?,?)";
		$dbh->do($SQL, undef, $reqid, $borrower_id, $borrower_id, "Message", "Trying next source");
		
		# begin the ILL conversation
		$SQL = "INSERT INTO request (requester, current_source_sequence_number, chain_id) values (?,?,?)";
		$dbh->do($SQL, undef, $borrower_id, $ary[1], $gcr[1]);
		my $newRequestId = $dbh->last_insert_id(undef,undef,undef,undef,{sequence=>'request_seq'});
		
		$SQL = "INSERT INTO requests_active (request_id, msg_from, msg_to, status) VALUES (?,?,?,?)";
		$retval = $dbh->do($SQL, undef, $newRequestId, $borrower_id, $ary[0], 'ILL-Request');
		
		# mark this source as tried
		$dbh->do("update sources set request_id=?, tried=true where group_id=? and sequence_number=?", undef, $newRequestId, $gcr[0], $ary[1]);
	    
		$return_data_href->{ success } = $retval;
		$return_data_href->{ status } = "Message";
		$return_data_href->{ message } = "Trying next source";

	    } else {
		$SQL = "insert into requests_active (request_id, msg_from, msg_to, status, message) values (?,?,?,?,?)";
		$dbh->do($SQL, undef, $reqid, $borrower_id, $borrower_id, "Message", "No further sources");
		$return_data_href->{ success } = 0;
		$return_data_href->{ status } = "Message";
		$return_data_href->{ message } = "No further sources";
		$return_data_href->{ alert_text } = "There were no further sources.\nThis request will remain here until you acknowledge 'No further sources'\n in overrides.";
	    }
	} else {
	    $return_data_href->{ success } = 0;
	    $return_data_href->{ status } = "Could not force cancellation/try-next-lender";
	    $return_data_href->{ message } = "Lender has already answered.";
	    $return_data_href->{ alert_text } = "The lender has already answered; if they could not fill the request, you can try the next lender from the Unfilled page.";
	}
    }

    case "bClose" {
	# borrowing override
	$borrower_id = $href->{"borrower_id"};
	$lender_id = $href->{"lender_id"};
	# can only close if the the borrower has returned but the lender hasn't checked in yet
	my $cntAnswers = $dbh->selectrow_array( "select count(*) from requests_active where request_id=? and msg_from=? and status='Returned' and request_id not in (select request_id from requests_active where request_id=? and status='Checked-in')", undef, $reqid, $borrower_id, $reqid );
	if ((defined $cntAnswers) && ($cntAnswers == 1)) {
	    $message = $href->{"borrower"} . " returned item but " . $href->{"lender"} . " has not checked it in";
	    # borrower sends a message about overriding
	    $retval = $dbh->do( $SQL, undef, $reqid, $borrower_id, $lender_id, $status, $message );
	    # force the ILL to be marked as Checked-in by the lender
	    $retval = $dbh->do( $SQL, undef, $reqid, $lender_id, $borrower_id, 'Checked-in', "override by $href->{borrower}" );	
	    # ...and move to history
	    $retval = move_to_history( $dbh, $reqid );
	    $return_data_href->{ success } = $retval;
	    $return_data_href->{ status } = "Checked-in";
	    $return_data_href->{ message } = "override";
	} else {
	    $return_data_href->{ success } = 0;
	    $return_data_href->{ status } = "Could not force check-in";
	    $return_data_href->{ message } = "Request not returned or already checked in.";
	    $return_data_href->{ alert_text } = "Could not close this request:\neither you have not marked the request as 'Returned'\nor the lender has already checked it in.";
	}
    }

    case "bReturned" {
	# lending override
	$borrower_id = $href->{"borrower_id"};
	$lender_id = $href->{"lender_id"};
	$message = $href->{"borrower"} . " has returned the item to " . $href->{"lender"} . " but did not mark it as 'Returned'";
	# can only Return if the the borrower has received but not yet returned
	my $cntAnswers = $dbh->selectrow_array( "select count(*) from requests_active where request_id=? and msg_to=? and status='Received' and request_id not in (select request_id from requests_active where request_id=? and status='Returned')", undef, $reqid, $lender_id, $reqid );
	if ((defined $cntAnswers) && ($cntAnswers == 1)) {
	    # lender sends a message about overriding
	    $retval = $dbh->do( $SQL, undef, $reqid, $lender_id, $borrower_id, $status, $message );
	    # force the ILL to be marked as Returned by the borrower
	    $retval = $dbh->do( $SQL, undef, $reqid, $borrower_id, $lender_id, 'Returned', "override by $href->{lender}" );	
	    # lender check-in and move to history
	    $retval = $dbh->do( $SQL, undef, $reqid, $lender_id, $borrower_id, 'Checked-in', "" );
	    $retval = move_to_history( $dbh, $reqid );
	    $return_data_href->{ success } = $retval;
	    $return_data_href->{ status } = "Returned";
	    $return_data_href->{ message } = "override";
	} else {
	    $return_data_href->{ success } = 0;
	    $return_data_href->{ status } = "Could not force return";
	    $return_data_href->{ message } = "Request not received or already returned.";
	    $return_data_href->{ alert_text } = "Could not mark this request as Returned:\neither the borrower has not Received yet,\nor they have already marked it as 'Returned'.";
	}
    }

    case "bDueDate" {
	# lending override
	print STDERR "bDueDate\n";
	$borrower_id = $href->{"borrower_id"};
	$lender_id = $href->{"lender_id"};
	if ($data =~ m!^((?:19|20)\d\d)[- /.](0[1-9]|1[012])[- /.](0[1-9]|[12][0-9]|3[01])$!) {
	    # At this point, $1 holds the year, $2 the month and $3 the day of the date entered
	    $message = "due " . $1 . "-" . $2 . "-" . $3;
	    print STDERR "$data becomes $message\n";

	    # can only change due date if the the borrower has not received yet
	    my $cntAnswers = $dbh->selectrow_array( "select count(*) from requests_active where request_id=? and msg_to=? and status='Shipped' and request_id not in (select request_id from requests_active where request_id=? and status='Received')", undef, $reqid, $borrower_id, $reqid );
	    if ((defined $cntAnswers) && ($cntAnswers == 1)) {
		print STDERR "ok to update, message [$message], reqid [$reqid], lender_id [$lender_id], borrower_id [$borrower_id]\n";
		# specify message like 'due%' so we don't overwrite an overridden ship (which will have a message like 'override by XXXX')
		$retval = $dbh->do( "update requests_active set message=? where request_id=? and msg_from=? and msg_to=? and status='Shipped' and (message like 'due%' or message='')", undef, $message, $reqid, $lender_id, $borrower_id );
		$return_data_href->{ success } = $retval;
		$return_data_href->{ status } = "Shipped";
		$return_data_href->{ message } = $message;
	    } else {
		print STDERR "NOT ok to update, message [$message], reqid [$reqid], lender_id [$lender_id], borrower_id [$borrower_id]\n";
		$return_data_href->{ success } = 0;
		$return_data_href->{ status } = "Shipped";
		$return_data_href->{ message } = "Cannot override - borrower has received";
	    }
	} else {
	    $return_data_href->{ success } = 0;
	    $return_data_href->{ status } = "Shipped";
	    $return_data_href->{ message } = "Invalid date";
	    $return_data_href->{ alert_text } = "Invalid date or date format.";
	}
	print STDERR Dumper( $return_data_href );
    }

    else {
	$borrower_id = $href->{"borrower_id"};
	$lender_id = $href->{"lender_id"};
	$message = "unknown override: [$override]";
	$retval = $dbh->do( $SQL, undef, $reqid, $borrower_id, $lender_id, $status, $message );
	$return_data_href->{ success } = $retval;
	$return_data_href->{ status } = "error";
	$return_data_href->{ message } = $message;
    }
}

# sql to add to the request conversation

$dbh->disconnect;
#print "Content-Type:application/json\n\n" . to_json( { success => $retval } );
print "Content-Type:application/json\n\n" . to_json( $return_data_href );


sub move_to_history {
    my $dbh = shift;
    my $reqid = shift;

    $dbh->{AutoCommit} = 0;  # enable transactions, if possible
    $dbh->{RaiseError} = 1;
    my $rSuccess;

    eval {
    my $SQL;
    # get the request_id, chain_id, and group_id from the (live) request
    $SQL = "select g.group_id, c.chain_id, r.id from request_group g left join request_chain c on c.group_id = g.group_id left join request r on r.chain_id=c.chain_id where r.id=?";
    my @gcr = $dbh->selectrow_array( $SQL, undef, $reqid );
    print STDERR "override - move-to-history: gid [$gcr[0]], cid [$gcr[1]], rid [$gcr[2]]\n";
    
    # see if the group already exists in history
    $SQL = "select count(group_id) from history_group where group_id=?";
    my @hg = $dbh->selectrow_array( $SQL, undef, $gcr[0] );
    if ((@hg) && ($hg[0] == 0)) {
	# not yet in history_group, so add it
	$SQL = "insert into history_group (group_id, copies_requested, title, author, medium, requester, patron_barcode, note) select group_id, copies_requested, title, author, medium, requester, patron_barcode, note from request_group where group_id=?";
	$dbh->do( $SQL, undef, $gcr[0] );
	print STDERR "override - move-to-history: request_group added to history_group\n";
    } else {
	print STDERR "override - move-to-history: request_group already exists in history_group\n";
    }

    # see if the chain already exists in history
    # (this should not happen... entire chain moved at once)
    $SQL = "select count(chain_id) from history_chain where chain_id=?";
    my @hc = $dbh->selectrow_array( $SQL, undef, $gcr[1] );
    if ((@hc) && ($hc[0] == 0)) {
	# not yet in history_chain, so add it
	$SQL = "insert into history_chain (group_id, chain_id) values (?,?)";
	$dbh->do( $SQL, undef, $gcr[0], $gcr[1] );
	print STDERR "override - move-to-history: request_chain added to history_chain\n";
    } else {
	print STDERR "override - move-to-history: request_chain already exists in history_chain!\n";
    }

    # get all of the requests for this chain
    my $rClosed = 0;
    my $rHistory = 0;
    my $rActive = 0;
    my $rSources = 0;
    my $rRequest = 0;
    my $rChains = 0;

    $SQL = "select id from request where chain_id=?";
    my $chained_requests_aref = $dbh->selectall_arrayref( $SQL, undef, $gcr[1] );
    print STDERR "override - move-to-history: moving chain to history\n";
    foreach my $req_aref (@$chained_requests_aref) {
	my $chained_req = $req_aref->[0];
	print STDERR "override - move-to-history: chain [" . $gcr[1] . "], request [$chained_req]\n";

	# attempts doesn't make sense any more with request_groups / request_chains... need to figure out what to do here.
	# For now, leave as-is.
	$SQL = "insert into request_closed (id,requester,chain_id) (select id,requester, chain_id from request where id=?)";
	$rClosed = $dbh->do( $SQL, undef, $chained_req );
	print STDERR "override - move-to-history: request [$chained_req] inserted into request_closed\n";

	$SQL = "insert into requests_history (request_id, ts, msg_from, msg_to, status, message) (select request_id, ts, msg_from, msg_to, status, message from requests_active where request_id=?);";
	$rHistory = ($dbh->do( $SQL, undef, $chained_req ) ? 1 : 0);
	print STDERR "override - move-to-history: associated requests_active inserted into requests_history\n";

	$SQL = "delete from requests_active where request_id=?";
	$rActive = ($dbh->do( $SQL, undef, $chained_req ) ? 1 : 0);
	print STDERR "override - move-to-history: requests_active deleted for reqid $chained_req\n";

	# sources.request_id is an fkey.  Can't delete the request until that's reset.
	$SQL = "update sources set request_id=NULL where request_id=?";
	$rSources = ($dbh->do( $SQL, undef, $chained_req ) ? 1 : 0);
	print STDERR "override - move-to-history: sources referencing this request have been nulled\n";

	$SQL = "delete from request where id=?";
	$rRequest = $dbh->do( $SQL, undef, $chained_req );
	print STDERR "override - move-to-history: request deleted\n";
    }

    $SQL = "select count(id) from request where chain_id=?";
    my @cnt = $dbh->selectrow_array( $SQL, undef, $gcr[1] );
    if ((@cnt) && ($cnt[0] == 0)) {
	# no requests left in this chain
	$SQL = "delete from request_chain where chain_id=?";
	$dbh->do( $SQL, undef, $gcr[1] );
	print STDERR "override - move-to-history: no requests left in this chain, chain deleted\n";
    } else {
	# this should not happen.
	print STDERR "override - move-to-history: strange... still requests in this chain, chain not deleted\n";
    }
    @cnt = undef;

    $SQL = "select count(group_id) from request_chain where group_id=?";
    @cnt = $dbh->selectrow_array( $SQL, undef, $gcr[0] );
    if ((@cnt) && ($cnt[0] == 0)) {
	# no chains left in this group
	$SQL = "delete from request_group where group_id=?";
	$rChains = $dbh->do( $SQL, undef, $gcr[0] );
	print STDERR "override - move-to-history: no chains left in this group, group deleted\n";

	# we don't need the sources for history
	$SQL = "delete from sources where group_id=?";
	$rSources = ($dbh->do( $SQL, undef, $gcr[0] ) ? 1 : 0);
	print STDERR "override - move-to-history: no further need of sources, sources deleted\n";
    } else {
	print STDERR "override - move-to-history: still chains in this group, group not deleted\n";
    }

    $dbh->commit;   # commit the changes if we get this far
    };
    if ($@) {
	warn "Transaction aborted because $@";
	# now rollback to undo the incomplete changes
	# but do it in an eval{} as it may also fail
	eval { $dbh->rollback };
	# add other application on-error-clean-up code here
    } else {
	$rSuccess = 1;
    }

    return $rSuccess;
}


