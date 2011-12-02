// receiving.js
function build_table( data ) {
//    alert( 'in build_table' );
    var myTable = document.createElement("table");
    myTable.setAttribute("id","gradient-style");
    var tHead = myTable.createTHead();
    var row = tHead.insertRow(-1);
    var cell;
    // Can't just use:
    // cell = row.insertCell(-1); cell.innerHTML = "ID";
    // ...because insertCell inserts TD elements, and our CSS uses TH for header cells.
    
    cell = document.createElement("TH"); cell.innerHTML = "ID"; row.appendChild(cell);
    cell = document.createElement("TH"); cell.innerHTML = "Title"; row.appendChild(cell);
    cell = document.createElement("TH"); cell.innerHTML = "Author"; row.appendChild(cell);
    cell = document.createElement("TH"); cell.innerHTML = "Patron"; row.appendChild(cell);
    cell = document.createElement("TH"); cell.innerHTML = "From"; row.appendChild(cell);
    cell = document.createElement("TH"); cell.innerHTML = "From (ID)"; row.appendChild(cell);
    cell = document.createElement("TH"); cell.innerHTML = "Timestamp"; row.appendChild(cell);
    cell = document.createElement("TH"); cell.innerHTML = "Due date"; row.appendChild(cell);
    cell = document.createElement("TH"); cell.innerHTML = "Receive"; row.appendChild(cell);
    
    var tFoot = myTable.createTFoot();
    row = tFoot.insertRow(-1);
    cell = row.insertCell(-1); cell.colSpan = "9"; cell.innerHTML = "As items are received, they are removed from this list.  You can see the status of all of your active ILLs in the \"Current ILLs\" screen.";
    
    // explicit creation of TBODY element to make IE happy
    var tBody = document.createElement("TBODY");
    myTable.appendChild(tBody);
    
//    alert('building rows');
    for (var i=0;i<data.receiving.length;i++) 
    {
//	alert (data.receiving[i].id+" "+data.receiving[i].msg_from+" "+data.receiving[i].call_number+" "+data.receiving[i].author+" "+data.receiving[i].title+" "+data.receiving[i].ts); //further debug
        row = tBody.insertRow(-1); row.id = 'req'+data.receiving[i].id;
        cell = row.insertCell(-1); cell.innerHTML = data.receiving[i].id;
        cell = row.insertCell(-1); cell.innerHTML = data.receiving[i].title;
        cell = row.insertCell(-1); cell.innerHTML = data.receiving[i].author;
        cell = row.insertCell(-1); cell.innerHTML = data.receiving[i].patron_barcode;
        cell = row.insertCell(-1); cell.innerHTML = data.receiving[i].from;
        cell = row.insertCell(-1); cell.innerHTML = data.receiving[i].msg_from;
        cell = row.insertCell(-1); cell.innerHTML = data.receiving[i].ts;
        cell = row.insertCell(-1); cell.innerHTML = data.receiving[i].message;
        cell = row.insertCell(-1); 

	var divResponses = document.createElement("div");
	divResponses.id = 'divResponses'+data.receiving[i].id;

	var b1 = document.createElement("input");
	b1.type = "button";
	b1.value = "Received";
	var requestId = data.receiving[i].id;
	b1.onclick = make_receiving_handler( requestId );
	divResponses.appendChild(b1);
	
	cell.appendChild( divResponses );
    }
    
    document.getElementById('mylistDiv').appendChild(myTable);
    
    toggleLayer("waitDiv");
    toggleLayer("mylistDiv");
}

// Explanation of why we need a function to create the buttons' onclick handlers:
// http://www.webdeveloper.com/forum/archive/index.php/t-100584.html
// Short answer: scoping and closures

function make_receiving_handler( requestId ) {
    return function() { receive( requestId ) };
}

function receive( requestId ) {
    // NOTE: this code will find table rows based on cell contents...
    // ...as we now have <tr id='xxx'>, there's an easier way....

    // Returns [{reqid: 12, msg_to: '101'}, 
    //          {reqid: 15, msg_to: '98'},
    // Note that nth-child uses 1-based indexing, not 0-based
    var parms = $('#gradient-style tbody tr').map(function() {
	// $(this) is used more than once; cache it for performance.
	var $row = $(this);
	
	// For each row that's "mapped", return an object that
	//  describes the first and second <td> in the row.
	if ($row.find(':nth-child(1)').text() == requestId) {
	    return {
		reqid: $row.find(':nth-child(1)').text(),
		msg_to: $row.find(':nth-child(6)').text(),  // sending TO whoever original was FROM
		lid: $("#lid").text(),
		status: "Received",
		message: ""
	    }
	} else {
	    return null;
	};
    }).get();

    $.getJSON('/cgi-bin/change-request-status.cgi', parms[0],
	      function(data){
//		  alert('change request status: '+data+'\n'+parms[0].status);
	      })
	.success(function() {
	    //alert('success');
	    // print slip (single) / add to slip page (multi) / do nothing (none)
	})
	.error(function() {
	    alert('error');
	})
	.complete(function() {
	    // slideUp doesn't work for <tr>
	    $("#req"+requestId).fadeOut(400, function() { $(this).remove(); }); // toast the row
	});
}


function toggleLayer( whichLayer )
{
    var elem, vis;
    if( document.getElementById ) // this is the way the standards work
	elem = document.getElementById( whichLayer );
    else if( document.all ) // this is the way old msie versions work
	elem = document.all[whichLayer];
    else if( document.layers ) // this is the way nn4 works
	elem = document.layers[whichLayer];

    vis = elem.style;
    // if the style.display value is blank we try to figure it out here
    if(vis.display==''&&elem.offsetWidth!=undefined&&elem.offsetHeight!=undefined)
	vis.display = (elem.offsetWidth!=0&&elem.offsetHeight!=0)?'block':'none';
    vis.display = (vis.display==''||vis.display=='block')?'none':'block';
    //    alert('toggled ' + whichLayer);
}

function set_primary_tab(tab_id) {
    document.getElementById(tab_id).className='current_tab';
}

function set_secondary_tab(tab_id) {
    document.getElementById(tab_id).className='current_tab';
}


