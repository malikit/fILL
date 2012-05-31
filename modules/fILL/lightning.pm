#
#    fILL - Free/Open-Source Interlibrary Loan management system
#    Copyright (C) 2011  David A. Christensen
#
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

package fILL::lightning;
use warnings;
use strict;
use base 'fILLbase';
use GD::Barcode;
use GD::Barcode::Code39;
use MIME::Base64;
use Data::Dumper;
#use Fcntl qw(LOCK_EX LOCK_NB);

my %SPRUCE_TO_MAPLIN = (
    'MWPL' => 'MWPL',
    'ALTONA' => 'MAOW',
    'BOISSEVAIN' => 'MBOM',
    'MANITOU' => 'MMA',
    'MIAMI' => 'MMIOW',
    'MORDEN' => 'MMOW',
    'STEROSE' => 'MSTR',
    'WINKLER' => 'MWOW',
    'AB' => 'MWP',
    'MWP' => 'MWP',
);

#--------------------------------------------------------------------------------
# Define our runmodes
#
sub setup {
    my $self = shift;
    $self->start_mode('lightning_search_form');
    $self->error_mode('error');
    $self->mode_param('rm');
    $self->run_modes(
	'lightning_search_form'    => 'lightning_search_process',
	'lightning_request_form'   => 'lightning_request_process',
	'request'                  => 'request_process',
	'complete_the_request'     => 'complete_the_request_process',
	'pull_list'                => 'pull_list_process',
	'respond'                  => 'respond_process',
	'unfilled'                 => 'unfilled_process',
	'receive'                  => 'receiving_process',
	'renewals'                 => 'renewals_process',
	'returns'                  => 'returns_process',
	'overdue'                  => 'overdue_process',
	'renew_answer'             => 'renew_answer_process',
	'checkins'                 => 'checkins_process',
	'history'                  => 'history_process',
	'live_requests'            => 'live_requests_process',
	);
}

#--------------------------------------------------------------------------------
#
#
sub complete_the_request_process {
    my $self = shift;
    my $q = $self->query;

    my $pbarcode = $q->param('pbarcode');
    my $request_note = $q->param('request_note');
    my $reqid = $q->param('request_id');
    if ($pbarcode) {
	my $SQL = "UPDATE request SET patron_barcode=?, current_target=1 WHERE id=?";
	$self->dbh->do($SQL, undef, $pbarcode, $reqid);  # do some error checking....!
    }
    if ($request_note) {
	my $SQL = "UPDATE request SET note=? WHERE id=?";
	$self->dbh->do($SQL, undef, $request_note, $reqid);  # do some error checking....!
    }

    # get the request
    my $hr_req = $self->dbh->selectrow_hashref("SELECT * FROM request WHERE id=?",undef,$reqid);
    my $requester = $hr_req->{requester};
    my $seq = $hr_req->{current_target}; # where are we in the sequence of sources? (sequence #)

    # get the first source
    my $hr_src = $self->dbh->selectrow_hashref("SELECT * FROM sources WHERE request_id=? and sequence_number=?",undef,$reqid,$seq);
    my $source_library = $hr_src->{library};

    # begin the ILL conversation
    my $SQL = "INSERT INTO requests_active (request_id, msg_from, msg_to, status) VALUES (?,?,?,?)";
    $self->dbh->do($SQL, undef, $reqid, $requester, $source_library, 'ILL-Request');

    # does the selected source library want immediate notification, by email, of new requests?
    my @notify = $self->dbh->selectrow_array("SELECT request_email_notification, email_address FROM libraries WHERE lid=?",
					     undef,$source_library);
    if ($notify[0]) {
	send_notification($self,$notify[1],$reqid);
    }

    my $template = $self->load_tmpl('search/request_placed.tmpl');	
    $template->param( pagetitle => "fILL Request has been placed",
		      username => $self->authen->username,
		      lid => $requester,
		      request_id => $reqid,
	);
    return $template->output;
}

#--------------------------------------------------------------------------------
#
#
sub lightning_search_process {
    my $self = shift;
    my $q = $self->query;

    my $template = $self->load_tmpl('search/lightning.tmpl');	
#    $template->param( pagetitle => "fILL Lightning Search",
#		      username => $self->authen->username,
#		      sessionid => $self->session->id(),
#	);
    return $template->output;
}


#--------------------------------------------------------------------------------
#
#
sub pull_list_process {
    my $self = shift;
    my $q = $self->query;

    my $lid = get_lid_from_symbol($self, $self->authen->username);  # do error checking!

    # sql to get requests to this library, which this library has not responded to yet
    my $SQL = "select b.barcode, r.title, r.author, r.note, date_trunc('second',ra.ts) as ts, l.name as from, l.library, s.call_number from request r left join requests_active ra on (r.id = ra.request_id) left join library_barcodes b on (ra.msg_from = b.borrower and b.lid=?) left join sources s on (s.request_id = ra.request_id and s.library = ra.msg_to) left join libraries l on ra.msg_from = l.lid where ra.msg_to=? and ra.status='ILL-Request' and ra.request_id not in (select request_id from requests_active where msg_from=?) order by s.call_number";

    my $pulls = $self->dbh->selectall_arrayref($SQL, { Slice => {} }, $lid, $lid, $lid );

    # generate barcodes (code39 requires '*' as start and stop characters
    foreach my $request (@$pulls) {
	if (( $request->{barcode} ) && ( $request->{barcode} =~ /\d+/)) {
	    $request->{"barcode_image"} = encode_base64(GD::Barcode::Code39->new( '*' . $request->{barcode} . '*' )->plot->png);
	}
    }

    my $template = $self->load_tmpl('search/pull_list.tmpl');	
    $template->param( pagetitle => $self->authen->username . " Pull-list",
		      username => $self->authen->username,
		      lid => $lid,
		      pulls => $pulls,
	);
    return $template->output;
    
}

#--------------------------------------------------------------------------------
#
# I think the ordering of the sources needs to be based on something like:
# select l.lid, l.name, count(rh1.request_id) as borrowed, count(rh2.request_id) as loaned from libraries l left join requests_history rh1 on rh1.msg_from=l.lid left join requests_history rh2 on rh2.msg_to=l.lid where rh1.status = 'Received' and rh2.status = 'Shipped' group by l.lid, l.name;
#
# that is, find how many items each library has borrowed and how many loaned.  Then calculate (loaned - borrowed) and sort by that
# (so a library that has borrowed more than it has loaned will end up with a lower number (in fact, negative))
sub request_process {
    my $self = shift;
    my $q = $self->query;

    my @inParms = $q->param;
    my @parms;
    my %sources;
    foreach my $parm_name (@inParms) {
	my %p;
	$p{parm_name} = $parm_name;
	$p{parm_value} = $q->param($parm_name);
	push @parms, \%p;

	if ($parm_name =~ /_\d+/) {
	    my ($pname,$num) = split /_/,$parm_name;
	    $sources{$num}{$pname} = $q->param($parm_name);
	}
    }

    my @sources;
    foreach my $num (sort keys %sources) {
	if ($sources{$num}{'symbol'} eq 'SPRUCE') {
	    $self->log->debug( "Callno: " . $sources{$num}{'sprucecallno'} );
	    # split the combined sprucelocation into separate locations
	    my @locs = split /\,/, $sources{$num}{'sprucelocation'};
	    my @callnos = split /\,/, $sources{$num}{'sprucecallno'};
	    my %spruce_callno = ();
	    for (my $i=0; $i < @locs; $i++) {
		$spruce_callno{ $locs[$i] } = $callnos[$i];
	    }

	    delete $sources{$num}{'sprucelocation'};
	    delete $sources{$num}{'sprucecallno'};

	    my @holdings = split /\,/, $sources{$num}{'holding'};
#	    $self->log->debug( Dumper(@holdings) );
	    my %spruce_holding = ();
	    foreach my $holding (@holdings) {
		foreach my $key (keys %SPRUCE_TO_MAPLIN) {
		    if ( $holding =~ m/($key) \d{14}/ ) {
			$spruce_holding{$key} = $holding;
		    }
		}
	    }
#	    $self->log->debug( Dumper(%spruce_holding) );

	    my %seen;
	    foreach my $loc (@locs) {
		next if $seen{$loc};
		$seen{$loc} = 1;
		my %src;
		foreach my $pname (keys %{$sources{$num}}) {
		    $src{$pname} = $sources{$num}{$pname};
		}
		$src{'symbol'} = $SPRUCE_TO_MAPLIN{ $loc };
		$src{'holding'} = $spruce_holding{ $loc };
		$src{'callno'} = $spruce_callno{ $loc };
		push @sources, \%src;
	    }
	} else {
	    # non-Spruce
	    my %src;
	    foreach my $pname (keys %{$sources{$num}}) {
		next if (($pname eq 'sprucelocation') || ($pname eq 'sprucecallno'));
		$src{$pname} = $sources{$num}{$pname};
	    }
	    push @sources, \%src;
	}
    }
    $self->log->debug( Dumper(@sources) );

    # Get this user's (requester's) library id
    my $requester = get_lid_from_symbol($self, $self->authen->username);  # do error checking!
    if (not defined $requester) {
	# should never get here...
	# go to some error page.
    }

    my $title = $q->param('title');
    my $author = $q->param('author');

    # These should be atomic...
    # create the request (sans patron barcode)
    $self->dbh->do("INSERT INTO request (title,author,requester,current_target) VALUES (?,?,?,?)",
		   undef,
		   $title,
		   $author,
		   $requester,
		   0                                   # no source yet (aka request isn't complete until patron barcode is in
	);
    my $reqid = $self->dbh->last_insert_id(undef,undef,undef,undef,{sequence=>'request_seq'});
    # ...end of atomic

    # remove duplicate entries for a given library (they may have multiple holdings)
    my %seen = ();
    my @unique_sources = grep { ! $seen{ $_->{'symbol'} }++ } @sources;

    # ...and the sources list (worry about proper order after this code is working!)
    my $sequence = 1;
    my $SQL = "INSERT INTO sources (request_id, sequence_number, library, call_number) VALUES (?,?,?,?)";
    foreach my $src (@unique_sources) {
	my $hr_id = $self->dbh->selectrow_hashref(
	    "SELECT lid FROM libraries WHERE name=?",
	    undef,
	    $src->{symbol},
	    );
	my $lenderID = $hr_id->{lid};
	next unless defined $lenderID;
	$self->dbh->do($SQL,
		       undef,
		       $reqid,
		       $sequence++,
		       $lenderID,
		       $src->{"callno"},
	    );
    }


    my $template = $self->load_tmpl('search/make_request.tmpl');	
    $template->param( pagetitle => "fILL Request an ILL",
		      username => $self->authen->username,
		      lid => $requester,
		      request_id => $reqid,
		      title => $q->param('title') || ' ',
		      author => $q->param('author') || ' ',
		      sources => \@sources,
	);
    return $template->output;
    
}

#--------------------------------------------------------------------------------
#
#
sub respond_process {
    my $self = shift;
    my $q = $self->query;

    my $lid = get_lid_from_symbol($self, $self->authen->username);  # do error checking!

    my $template = $self->load_tmpl('search/respond.tmpl');	
    $template->param( pagetitle => "Respond to ILL requests",
		      username => $self->authen->username,
		      lid => $lid,
	);
    return $template->output;
    
}

#--------------------------------------------------------------------------------
#
#
sub receiving_process {
    my $self = shift;
    my $q = $self->query;

    my $lid = get_lid_from_symbol($self, $self->authen->username);  # do error checking!

    my $template = $self->load_tmpl('search/receiving.tmpl');	
    $template->param( pagetitle => "Receive items to fill your requests",
		      username => $self->authen->username,
		      lid => $lid,
	);
    return $template->output;
    
}

#--------------------------------------------------------------------------------
#
#
sub renewals_process {
    my $self = shift;
    my $q = $self->query;

    my $lid = get_lid_from_symbol($self, $self->authen->username);  # do error checking!

    my $template = $self->load_tmpl('search/renewals.tmpl');	
    $template->param( pagetitle => "Ask for renewals on borrowed items",
		      username => $self->authen->username,
		      lid => $lid,
	);
    return $template->output;
    
}

#--------------------------------------------------------------------------------
#
#
sub renew_answer_process {
    my $self = shift;
    my $q = $self->query;

    my $lid = get_lid_from_symbol($self, $self->authen->username);  # do error checking!

    my $template = $self->load_tmpl('search/renew-answer.tmpl');	
    $template->param( pagetitle => "Respond to renewal requests",
		      username => $self->authen->username,
		      lid => $lid,
	);
    return $template->output;
    
}

#--------------------------------------------------------------------------------
#
#
sub returns_process {
    my $self = shift;
    my $q = $self->query;

    my $lid = get_lid_from_symbol($self, $self->authen->username);  # do error checking!

    my $template = $self->load_tmpl('search/returns.tmpl');	
    $template->param( pagetitle => "Return items to lending libraries",
		      username => $self->authen->username,
		      lid => $lid,
	);
    return $template->output;
    
}

#--------------------------------------------------------------------------------
#
#
sub overdue_process {
    my $self = shift;
    my $q = $self->query;

    my $lid = get_lid_from_symbol($self, $self->authen->username);  # do error checking!

    my $template = $self->load_tmpl('search/overdue.tmpl');	
    $template->param( pagetitle => "Overdue items to be returned to lender",
		      username => $self->authen->username,
		      lid => $lid,
	);
    return $template->output;
    
}

#--------------------------------------------------------------------------------
#
#
sub checkins_process {
    my $self = shift;
    my $q = $self->query;

    my $lid = get_lid_from_symbol($self, $self->authen->username);  # do error checking!

    my $template = $self->load_tmpl('search/checkins.tmpl');	
    $template->param( pagetitle => "Loan items to be checked back into your ILS",
		      username => $self->authen->username,
		      lid => $lid,
	);
    return $template->output;
    
}

#--------------------------------------------------------------------------------
#
#
sub history_process {
    my $self = shift;
    my $q = $self->query;

    my $lid = get_lid_from_symbol($self, $self->authen->username);  # do error checking!

    my $template = $self->load_tmpl('search/history.tmpl');	
    $template->param( pagetitle => "ILL history",
		      username => $self->authen->username,
		      lid => $lid,
	);
    return $template->output;
    
}

#--------------------------------------------------------------------------------
#
#
sub live_requests_process {
    my $self = shift;
    my $q = $self->query;

    my $lid = get_lid_from_symbol($self, $self->authen->username);  # do error checking!

    my $template = $self->load_tmpl('search/live-requests.tmpl');	
    $template->param( pagetitle => "Current ILLs",
		      username => $self->authen->username,
		      lid => $lid,
	);
    return $template->output;
    
}

#--------------------------------------------------------------------------------
#
#
sub unfilled_process {
    my $self = shift;
    my $q = $self->query;

    my $lid = get_lid_from_symbol($self, $self->authen->username);  # do error checking!

    my $template = $self->load_tmpl('search/unfilled.tmpl');	
    $template->param( pagetitle => "Unfilled ILL requests",
		      username => $self->authen->username,
		      lid => $lid,
	);
    return $template->output;
    
}

#--------------------------------------------------------------------------------
#
#
sub lightning_request_process_DEPRECATED {
    my $self = shift;
    my $q = $self->query;

    my $zname = $q->param('ztarget');
    $zname =~ s/^(.+) \(.+$/$1/;
    my $hr_zserver = $self->dbh->selectrow_hashref("SELECT id, email_address FROM zservers WHERE name=?", {}, $zname);
    
    my $hr_user = $self->dbh->selectrow_hashref("SELECT lid, email_address, library, mailing_address_line1, mailing_address_line2, mailing_address_line3 from libraries WHERE name=?", {}, $self->authen->username);
    
    my $from = "From: plslib1\@mts.net\n";
    my $to = "To: " . $hr_zserver->{'email_address'} . "\n";
    my $reply_to = "Reply-to: " . $hr_user->{'email_address'} . "\n";
    my $cc = "Cc: " . $hr_user->{'email_address'} . "\n";

    my $subject = "Subject: ILL Request: " . $q->param('title') . "\n";

    my $content = "This is an automatically generated request from fILL\n\n";
    $content .= $hr_user->{'library'} . " would like to request the following item\nfrom ";
    $content .= $zname . ":\n-------------------------------------\n";
    $content .= "Title : " . $q->param('title') . "\n";
    $content .= "Author: " . $q->param('author') . "\n";
    $content .= "Call #: " . $q->param('callno') . "\n";
    $content .= "Medium: " . $q->param('medium') . ", ";
    $content .= "PubDate " . $q->param('date') . ", ";
    $content .= "ISBN " . $q->param('isbn') . "\n";
    $content .= "Holding:" . $q->param('holding') . "\n";

    $content .= "\n-------------------------------------\n";
    $content .= "Requesting library: " . $self->authen->username . "\n\n";
    $content .= $hr_user->{'library'} . "\n";
    $content .= $hr_user->{'mailing_address_line1'} . "\n" if ($hr_user->{'mailing_address_line1'});
    $content .= $hr_user->{'mailing_address_line2'} . "\n" if ($hr_user->{'mailing_address_line2'});
    $content .= $hr_user->{'mailing_address_line3'} . "\n" if ($hr_user->{'mailing_address_line3'});

    $content .= "\n-------------------------------------\n";
    $content .= "Patron #: " . $q->param('patron') . "\n" if ($q->param('patron'));
    $content .= "Notes   : " . $q->param('notes') . "\n" if ($q->param('notes'));

    my $sent = $q->param('sent') || 0;
    my $error_sendmail = 0;
    my $sendmail = "/usr/sbin/sendmail -t";
    if ($q->param('send_email')) {
	eval {
	    open(SENDMAIL, "|$sendmail") or die "Cannot open $sendmail: $!";
	    #    print SENDMAIL $from;
	    print SENDMAIL $reply_to;
	    print SENDMAIL $to;
	    print SENDMAIL $cc;
	    print SENDMAIL $subject;
	    print SENDMAIL "Content-type: text/plain\n\n";
	    print SENDMAIL $content;
	    close(SENDMAIL);
	};
	if ($@) {
	    # sendmail blew up
	    $self->log->debug("sendmail blew up");
	    $error_sendmail = 1;
	    $content =~ s/This is an automatically generated request from fILL/fILL had a problem sending email.\nThis is a MANUAL request./;
	    $content = "--- copy from here ---\n" . $content . "\n--- copy to here ---\n";
	} else {
	    #$self->log->debug("sendmail sent request");
	    #$self->_update_ILL_stats($lid, $zid, $loc, $callno, $pubdate);
	    $sent = 1;
	}
    }

    my $template = $self->load_tmpl('search/lightning_request.tmpl');	
    $template->param( pagetitle => "fILL Lightning Request",
		      username => $self->authen->username,
		      from => $from,
		      to => $to,
		      cc => $cc,
		      reply_to => $reply_to,
		      subject => $subject,
		      content => $content,
		      error_sendmail => $error_sendmail,
		      sent => $sent,
		      ztarget => $q->param('ztarget'),
		      title => $q->param('title'),
		      author => $q->param('author'),
		      callno => $q->param('callno'),
		      medium => $q->param('medium'),
		      date => $q->param('date'),
		      isbn => $q->param('isbn'),
	);
    return $template->output;
}


#--------------------------------------------------------------------------------------------
sub send_notification {
    my $self = shift;
    my $to_email = shift;
    my $reqid = shift;

#    $self->log->info( "Source wants an email" );

    # for testing:
    my $old_email = $to_email;
    $to_email = 'David.Christensen@gov.mb.ca';

    my @tac = $self->dbh->selectrow_array("select r.title, r.author, s.call_number from request r left join sources s on s.request_id = r.id where r.id=?",
					  undef,$reqid);

    my $subject = "Subject: ILL Request: " . $tac[0] . "\n";
    my $content = "fILL notification\n\n";
    $content .= "You have a new request for the follwing item:\n";
    $content .= $tac[2] . "\t" . $tac[1] . "\t" . $tac[0] . "\n\n";
    $content .= "fILL: https://mintaka.gotdns.org/cgi-bin/lightning.cgi\n";
    $content .= "\n\n(debug): original email: $old_email\n";

#    $self->log->info( "To: $to_email\n$subject$content" );

    my $error_sendmail = 0;
    my $sendmail = "/usr/sbin/sendmail -t";

    eval {
        open(SENDMAIL, "|$sendmail") or die "Cannot open $sendmail: $!";
        print SENDMAIL 'To: ' . $to_email;
        print SENDMAIL $subject;
        print SENDMAIL "Content-type: text/plain\n\n";
        print SENDMAIL $content;
        close(SENDMAIL);
    };
    if ($@) {
        # sendmail blew up
        $self->log->debug("sendmail blew up");
    } else {
#        $self->log->debug("sendmail sent request");
    }

}

#--------------------------------------------------------------------------------------------
sub get_lid_from_symbol {
    my $self = shift;
    my $symbol = shift;
    # Get this user's (requester's) library id
    my $hr_id = $self->dbh->selectrow_hashref(
	"SELECT lid FROM libraries WHERE name=?",
	undef,
	$symbol
	);
    my $requester = $hr_id->{lid};
    return $requester;
}

1; # so the 'require' or 'use' succeeds
