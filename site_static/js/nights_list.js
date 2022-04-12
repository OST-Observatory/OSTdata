
var night_table = null;
var edit_status_window = null;
var edit_tags_window = null;
var all_tags = null;
var add_nights_window = null;


$(document).ready(function () {

    night_table = $('#datatable').DataTable({
    dom: 'l<"toolbar">frtip',
    serverSide: true,
    ajax: {
        url: '/api/nights/?format=datatables&keep=reduction_status_display',
        //adding "&keep=id,rank" will force return of id and rank fields
        data: get_filter_keywords,
        contentType: "application/json; charset=utf-8",
        dataType: "json",
    },
    searching: false,
    orderMulti: false, //Can only order on one column at a time
    order: [2],
    columns: [
        {  orderable:      false,
            className:      'select-control',
            data:           null,
            render: selection_render,
            width:          '10',
            searchable: false,
        },
        { data: 'name', render: name_render },
    //       { data: 'datasets', render: dataset_render , searchable: false, orderable: false },
        { data: 'tags', render: tag_render , searchable: false, orderable: false },
        { data: 'reduction_status', render: status_render,
            width: '70',
            className: "dt-center",
            searchable: false
        },
    ],
    paging: true,
    pageLength: 50,
    lengthMenu: [[10, 20, 50, 100, 1000], [10, 20, 50, 100, 1000]], // Use -1 for all.
    scrollY: $(window).height() - $('header').outerHeight(true) - 196,
    scrollCollapse: true,
    autoWidth: true,
    });

    //Add toolbar to table
    if (user_authenticated) {
        $("div.toolbar").html(
            "<input id='tag-button'  class='tb-button' value='Edit Tags' type='button' disabled>" +
            "<input id='status-button' class='tb-button' value='Change Status' type='button' disabled>" +
            "<input id='addnight-button' class='tb-button' value='Add Night' type='button'>" +
            "<input id='deletenight-button' class='tb-button' value='Delete Night(s)' type='button' disabled>");
    }
    else {$("div.toolbar").html(
        "<input id='tag-button'  class='tb-button' value='Edit Tags' type='button' disabled>" +
        "<input id='status-button' class='tb-button' value='Change Status' type='button' disabled>");
    };

    // Event listener to the two range filtering inputs to redraw on input
    $('#filter-form').submit( function(event) {
        event.preventDefault();
        night_table.draw();
    });

    // Make the filter button open the filter menu
    $('#filter-dashboard-button').on('click', openNav);
    function openNav() {
        $("#filter-dashboard").toggleClass('visible');
        $("#filter-dashboard-button").toggleClass('open');

        let text = $('#filter-dashboard-button').text();
        if (text === "filter_list"){
                $('#filter-dashboard-button').text("close");
        } else {
                $('#filter-dashboard-button').text("filter_list");
        }
    };

    // Check and uncheck tables rows
    $('#datatable tbody').on( 'click', 'td.select-control', function () {
        let tr = $(this).closest('tr');
        let row = night_table.row( tr );
        if ( $(row.node()).hasClass('selected') ) {
            deselect_row(row);
        } else {
            select_row(row);
        }
    } );

    $('#select-all').on('click', function () {
        if ( $(this).text() == 'check_box' | $(this).text() == 'indeterminate_check_box') {
            // Deselect all
            $(this).text('check_box_outline_blank')

            night_table.rows().every( function ( rowIdx, tableLoop, rowLoop ) {
                deselect_row(this); // Open this row
            });
        } else {
            // Close all rows
            $(this).text('check_box')

            night_table.rows().every( function ( rowIdx, tableLoop, rowLoop ) {
                select_row(this); // close the row
            });
        }
    });

    // Load the tags and add them to the tag selection list, and the tag edit window
    load_tags();

    //   Initialize edit windows
    edit_status_window = $("#editStatus").dialog({
        autoOpen: false,
        width: '150',
        modal: true,
    });

    edit_tags_window = $("#editTags").dialog({
        autoOpen: false,
        width: '250',
        modal: true,
    });

    add_nights_window = $("#addNights").dialog({
        autoOpen: false,
        width: '875',
        modal: true,
    });

    //   Event listeners for edit buttons
    $( "#status-button").click( openStatusEditWindow );
    $( "#tag-button").click( openTagEditWindow );
    $( "#deletenight-button").click( deleteNights );
    $( "#addnight-button").click( openAddNightsWindow );


    //   Reset check boxes when changing number of displayed objects in table
    $('#datatable_length').change(function() {
        night_table.rows().every( function (rowIdx, tableLoop, rowLoop) {
            deselect_row(this);
        });
    });

    //   Reset check boxes when switching to the next table page
    $('#datatable_paginate').click(function() {
        night_table.rows().every( function (rowIdx, tableLoop, rowLoop) {
            deselect_row(this);
        });
    });
});


// Table filter functionality

function get_filter_keywords( d ) {
    let selected_status = $("#status_options input:checked").map( function () { return this.value; }).get();
    let selected_tags = $("#tag_filter_options input:checked").map( function () { return parseInt(this.value); }).get();

    d = $.extend( {}, d, {
    "name": $('#filter_name').val(),
    "status": selected_status[0],
    "tags": selected_tags[0],

    } );

    return d
}


// Table renderers

function selection_render( data, type, full, meta ) {
    if ( $(night_table.row(meta['row']).node()).hasClass('selected') ){
        return '<i class="material-icons button select" title="Select">check_box</i>';
    } else {
        return '<i class="material-icons button select" title="Select">check_box_outline_blank</i>';
    }
}

function name_render( data, type, full, meta ) {
    // Create a link to the detail for the night name
    return "<a href='"+full['href']+"'>"+data+"</a>";
}

// function dataset_render( data, type, full, meta ) {
//    // Render the tags as a list of divs with the correct color.
//    var result = ""
//    var ds = data[0];
//    for (i = 0; i < data.length; i++) {
//       ds = data[i];
//       result += "<div class='dataset' style='background-color:"+ds.color+"' title='"+ds.name+"'>"+ "<a href='"+ds.href+"'>"+ds.name.charAt(0)+"</a></div>";
//    }
//    return result;
// }

function tag_render( data, type, full, meta ) {
    // Render the tags as a list of divs with the correct color.
    let result = ""
    let tag = data[0];
    for (i = 0; i < data.length; i++) {
        tag = data[i];
        result += "<div class='small-tag' style='border-color:"+tag.color+"' title='"+tag.description+"'>"+tag.name+"</div>";
    }
    return result;
}

function status_render( data, type, full, meta ) {
    return '<i class="material-icons status-icon ' + data +  '" title="' +
            full['reduction_status_display'] +'"></i>'
}


// Selection and Deselection of rows

function select_row(row) {
    $(row.node()).find("i[class*=select]").text('check_box')
    $(row.node()).addClass('selected');
    if ( night_table.rows('.selected').data().length < night_table.rows().data().length ) {
        $('#select-all').text('indeterminate_check_box');
    } else {
        $('#select-all').text('check_box');
    }
    $('#tag-button').prop('disabled', false)
    $('#status-button').prop('disabled', false)
    $('#deletenight-button').prop('disabled', false)
}

function deselect_row(row) {
    $(row.node()).find("i[class*=select]").text('check_box_outline_blank')
    $(row.node()).removeClass('selected');
    if ( night_table.rows('.selected').data().length === 0 ) {
        $('#select-all').text('check_box_outline_blank');
        $('#tag-button').prop('disabled', true)
        $('#status-button').prop('disabled', true)
        $('#deletenight-button').prop('disabled', true)
    } else {
        $('#select-all').text('indeterminate_check_box');
    }
}

// Edit status and tags functionality

function load_tags() {
    //   Clear tag options of the add-system form
    $("#id_tags").empty();

    //   Load all tags and add them to the window
    $.ajax({
        url : "/api/tags/",
        type : "GET",
        success : function(json) {
            all_tags = json.results;

            for (var i=0; i<all_tags.length; i++) {
                tag = all_tags[i];

                $('#tagOptions').append("<li title='" + tag['description'] +
                "'><input class='tristate' name='tags' type='checkbox' value='"
                + tag['pk'] + "' /> " + tag['name'] + "</li>" );

                $('#tag_filter_options').append(
                "<li><label><input id='id_status_" + i + "' name='tags' type='radio' value='" +
                tag['pk'] + "' /> " + tag['name'] + "</label></li>");

                //  Add tag options to add-system form
                $('#id_tags').append('<li><label for="id_tags_'+i+'"><input id="id_tags_'+i+'" type="checkbox" name="tags" value="'+tag['pk']+'"> '+tag['name'].replace(/\_/g, ' ')+'</label></li>')

            }

            $('#tagOptions').on('change', ':checkbox', function(event){ cylceTristate(event, this); });

            $('input[type=radio]').click(allow_unselect);

        },
        error : function(xhr,errmsg,err) {
            console.log(xhr.status + ": " + xhr.responseText);
            all_tags = [];
        }
    });
}

// ------------

function openStatusEditWindow() {
    edit_status_window = $("#editStatus").dialog({
        title: "Change Status",
        buttons: { "Update": updateStatus },
        close: function() { edit_status_window.dialog( "close" ); }
    });

    $("input[name='new-status']").prop('checked', false);
    edit_status_window.dialog( "open" );
}

function updateStatus() {
    let new_status = $("input[name='new-status']");
    if ( new_status.filter(':checked').length == 0 ) {
        $('#status-error').text('You need to select a status option!');
    } else {
        $('#status-error').text('');

        night_table.rows('.selected').every( function ( rowIdx, tableLoop, rowLoop ) {
            updateNightStatus(this, new_status.filter(':checked').val());
        });

    }
}

function updateNightStatus(row, status) {
    $.ajax({
        url : "/api/nights/"+row.data()['pk']+'/',
        type : "PATCH",
        data : { reduction_status: status },

        success : function(json) {
            edit_status_window.dialog( "close" );
            row.data(json).draw('page');
        },

        error : function(xhr,errmsg,err) {
            if (xhr.status == 403){
                $('#status-error').text('You have to be logged in to edit');
            }else{
                $('#status-error').text(xhr.status + ": " + xhr.responseText);
            }
            console.log(xhr.status + ": " + xhr.responseText);
        }
    });
}

// -------------

function openTagEditWindow() {
    edit_tags_window = $("#editTags").dialog({
        title: "Add/Remove Tags",
        buttons: { "Update": updateTags},
        close: function() { edit_tags_window.dialog( "close" ); }
    });

    //  Reset the counts per tag
    let all_tag_counts = {}
    for ( tag in all_tags ) {
        all_tag_counts[all_tags[tag]['pk']] = 0
    }

    //  Count how many objects each tag has
    night_table.rows('.selected').every( function ( rowIdx, tableLoop, rowLoop ) {
        let tags = this.data()['tags'];
        for (tag in tags) {
            all_tag_counts[tags[tag]['pk']] ++;
        }
    });

//     console.log(all_tag_counts);

    //  Set the checkbox states depending on the number of objects
    let selected_nights = night_table.rows('.selected').data().length
    for (tag in all_tag_counts) {
        //  Standard unchecked state, no object has this tag
        $(".tristate[value='"+tag+"']").prop("checked", false);
        $(".tristate[value='"+tag+"']").prop("indeterminate",false);
        $(".tristate[value='"+tag+"']").removeClass("indeterminate");

        if ( all_tag_counts[tag] == selected_nights ){
            //  Checked state, all objects have this tag
            $(".tristate[value='"+tag+"']").prop("checked", true);
        } else if ( all_tag_counts[tag] > 0 ) {
            //  Indeterminate state, some objects have this tag
            $(".tristate[value='"+tag+"']").prop("indeterminate", true);
            $(".tristate[value='"+tag+"']").addClass("indeterminate");
        }
    }
    edit_tags_window.dialog( "open" );
}

function updateTags() {
    // Get the checked and indeterminate tags
    let checked_tags = $(".tristate:checked:not(.indeterminate)").map(
        function () { return parseInt(this.value); } ).get();
    let indeterminate_tags = $(".tristate.indeterminate").map(
        function () { return parseInt(this.value); } ).get();

    console.log($(".tristate:checked:not(.indeterminate)"))
    console.log(checked_tags);
    console.log(indeterminate_tags);

    // Update the tags for each selected night
    night_table.rows('.selected').every( function ( rowIdx, tableLoop, rowLoop ) {
        let new_tags     = checked_tags;
        let current_tags = this.data()['tags'].map( function (x) { return x.pk; } );

        for ( tag in indeterminate_tags ) {
            if ( current_tags.indexOf(indeterminate_tags[tag]) > -1 ) {
                new_tags.push(indeterminate_tags[tag])
            }
        }
        update_night_tags(this, new_tags);
    });

}

function update_night_tags(row, new_tags){
    let night_pk = row.data()['pk']
    //    console.log(row.data());
    //    console.log(new_tags);
    $.ajax({
        url : "/api/nights/"+night_pk+'/',
        type : "PATCH",
        contentType: "application/json; charset=utf-8",

        data : JSON.stringify({ "tag_ids": new_tags }),

        success : function(json) {
            // update the table and close the edit window
            row.data( json ).draw('page');
            edit_tags_window.dialog( "close" );
        },

        error : function(xhr,errmsg,err) {
            if (xhr.status == 403){
                $('#tag-error').text('You have to be logged in to edit');
            }else{
                $('#tag-error').text(xhr.status + ": " + xhr.responseText);
            }
            console.log(xhr.status + ": " + xhr.responseText);
        }
    });
}

// -----

function deleteNights(){
    if (confirm('Are you sure you want to delete these Nights? This can NOT be undone!')===true){
    let rows = [];
    // get list of files
    night_table.rows('.selected').every(function (rowIdx, tableLoop, rowLoop) {
        let row = this;
        rows.push(row);
    });
    if ($('#progress-bar').length === 0) {
        $(".toolbar").append('<progress id="progress-bar" value="0" max="' + rows.length + '" class="progress-bar"></progress>')
    }
    else{
        $("#progress-bar").prop("max", rows.length)
        $("#progress-bar").val(0)
    }
    let n = 0;
    //   Set Promise -> evaluates to a resolved Promise
    let p = $.when()
    $.each(rows, function (index, row) {
        let pk = row.data()["pk"];
        //    Promise chaining using .then() + async function definition to allow
        //                                  the use of await
        p = p.then( async function () {
        await $.ajax({
            url : "/api/nights/"+pk+'/',
            type : "DELETE",
            success : function(json) {
                n += 1;
                night_table.row(row).remove().draw('full-hold');
                $('#select-all').text('check_box_outline_blank');
                $('#tag-button').prop('disabled', true);
                $('#status-button').prop('disabled', true);
                $('#deletenight-button').prop('disabled', true);
                $('#progress-bar').val(n)
            },
            error : function(xhr,errmsg,err) {
                n += 1;
                $('#progress-bar').val(n)
                if (xhr.status === 403){
                    alert('You have to be logged in to delete this nights.');
                } else{
                    alert(xhr.status + ": " + xhr.responseText);
                }
                console.log(xhr.status + ": " + xhr.responseText);
                },
            });
        });
        })
    }
}

// -------------


function openAddNightsWindow() {
   add_nights_window = $("#addNights").dialog({
      autoOpen: false,
      title: "Add Night(s)",
      close: function() { add_nights_window.dialog( "close" ); },
   });

   add_nights_window.dialog( "open" );
}


// ----------------------------------------------------------------------

// Tristate checkbox functionality
function cylceTristate(event, checkbox) {
    checkbox = $(checkbox);
    // Add extra indeterminate state in between unchecked and checked
    if ( checkbox.prop("checked") & !checkbox.hasClass("indeterminate") ) {
        checkbox.prop("checked", false);
        checkbox.prop("indeterminate", true);
        checkbox.addClass("indeterminate");
    } else if ( checkbox.prop("checked") & checkbox.hasClass("indeterminate") ) {
        checkbox.prop("indeterminate", false);
        checkbox.removeClass("indeterminate");
    }
}


// Allow unchecking of radio buttons in the filter window
$('input[type=radio]').click(allow_unselect);

function allow_unselect(e){
    if (e.ctrlKey) {
            $(this).prop('checked', false);
        }
}
