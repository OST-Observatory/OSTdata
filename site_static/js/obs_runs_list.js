
var run_table = null;
var edit_status_window = null;
var edit_tags_window = null;
var all_tags = null;
var add_runs_window = null;


$(document).ready(function () {

    //  Sanitize ajax calls if the site does not run in the web server root dir
    let script_name = $('#script_name').attr('name');
    if ( script_name == 'None' ) {
        script_name = '';
    }

    run_table = $('#datatable').DataTable({
        dom: 'l<"toolbar">frtip',
        serverSide: true,
        ajax: {
            url: script_name+'/api/runs/runs/?format=datatables&keep=reduction_status_display,n_img,n_ser,start_time,end_time,pk,spectroscopy',
            //adding "&keep=id,rank" will force return of id and rank fields
            data: get_filter_keywords,
            contentType: "application/json; charset=utf-8",
            dataType: "json",
        },
        searching: false,
        orderMulti: false, //Can only order on one column at a time
        order: [1],
        columns: [
            {  orderable:      false,
                className:      'select-control',
                data:           null,
                render: selection_render,
                width:          '10',
                searchable: false,
            },
            { data: 'name', render: name_render },
            { data: 'objects', render: objects_render },
            { data: 'photometry', render: observation_render },
            { data: 'n_fits', render: n_file_render },
            { data: 'expo_time', render: expo_time_render },
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
            // "<input id='addrun-button' class='tb-button' value='Add Observation run' type='button'>" +
            "<input id='deleterun-button' class='tb-button' value='Delete Observation run(s)' type='button' disabled>");
    }
    else {$("div.toolbar").html(
        "<input id='tag-button'  class='tb-button' value='Edit Tags' type='button' disabled>" +
        "<input id='status-button' class='tb-button' value='Change Status' type='button' disabled>");
    };

    // Event listener to the two range filtering inputs to redraw on input
    $('#filter-form').submit( function(event) {
        event.preventDefault();
        run_table.draw();
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
        let row = run_table.row( tr );
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

            run_table.rows().every( function ( rowIdx, tableLoop, rowLoop ) {
                deselect_row(this); // Open this row
            });
        } else {
            // Close all rows
            $(this).text('check_box')

            run_table.rows().every( function ( rowIdx, tableLoop, rowLoop ) {
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

    // add_runs_window = $("#addRuns").dialog({
    //     autoOpen: false,
    //     width: '875',
    //     modal: true,
    // });

    //   Event listeners for edit buttons
    $( "#status-button").click( openStatusEditWindow );
    $( "#tag-button").click( openTagEditWindow );
    $( "#deleterun-button").click( deleteRuns );
    // $( "#addrun-button").click( openAddRunsWindow );


    //   Reset check boxes when changing number of displayed objects in table
    $('#datatable_length').change(function() {
        run_table.rows().every( function (rowIdx, tableLoop, rowLoop) {
            deselect_row(this);
        });
    });

    //   Reset check boxes when switching to the next table page
    $('#datatable_paginate').click(function() {
        run_table.rows().every( function (rowIdx, tableLoop, rowLoop) {
            deselect_row(this);
        });
    });
});

// ----------------------------------------------------------------------
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

// ----------------------------------------------------------------------
// Table renderers

function selection_render( data, type, full, meta ) {
    if ( $(run_table.row(meta['row']).node()).hasClass('selected') ){
        return '<i class="material-icons button select" title="Select">check_box</i>';
    } else {
        return '<i class="material-icons button select" title="Select">check_box_outline_blank</i>';
    }
}

function name_render( data, type, full, meta ) {
    //  Create a link to the detail for the observation run name
    let start = full['start_time'].split('.')[0];
    let end = full['end_time'].split(" ")[1].split('.')[0];
    let href = "<a href='"+full['href']+"'>"+start+'-'+end+"</a>";
    return href;
}

function objects_render( data, type, full, meta ) {
    //  Create links to the objects
    let hrefs = [];
    for (i = 0; i < data.length; i++) {
    // for (obj in data) {
        let obj = data[i];
        hrefs.push("<a href='"+obj.href+"'> "+obj.name+"</a>");
    }
    return hrefs;
}

function observation_render(data, type, full, meta) {
    if (data && full['spectroscopy']) {
        return "<i class='material-icons status-icon valid' title='Spectra taken'></i> / <i class='material-icons status-icon valid' title='Photometry taken'></i>"
    } else if (data && !full['spectroscopy']) {
        return "<i class='material-icons status-icon valid' title='Spectra taken'></i> / <i class='material-icons status-icon invalid' title='No Photometry taken'></i>"
    } else if (!data && full['spectroscopy']) {
        return "<i class='material-icons status-icon invalid' title='No Spectra taken'></i> / <i class='material-icons status-icon valid' title='Photometry taken'></i>"
    } else {
        return "<i class='material-icons status-icon' title='Observation type not known'>question_mark</i> / <i class='material-icons status-icon' title='Observation type not known'>question_mark</i>"
    }
}

function n_file_render( data, type, full, meta ) {
    //  Render file numbers
    return data + "/" + full['n_img'] + "/" + full['n_ser'];
}

function expo_time_render( data, type, full, meta ) {
    //  Render exposure time to significant digits
    if (data === 0) {
        return '-'
    }
    if (data >= 1) {
        return data
    }
    return data.toFixed(2);
}

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

// ----------------------------------------------------------------------
// Selection and Deselection of rows

function select_row(row) {
    $(row.node()).find("i[class*=select]").text('check_box')
    $(row.node()).addClass('selected');
    if ( run_table.rows('.selected').data().length < run_table.rows().data().length ) {
        $('#select-all').text('indeterminate_check_box');
    } else {
        $('#select-all').text('check_box');
    }
    $('#tag-button').prop('disabled', false)
    $('#status-button').prop('disabled', false)
    $('#deleterun-button').prop('disabled', false)
}

function deselect_row(row) {
    $(row.node()).find("i[class*=select]").text('check_box_outline_blank')
    $(row.node()).removeClass('selected');
    if ( run_table.rows('.selected').data().length === 0 ) {
        $('#select-all').text('check_box_outline_blank');
        $('#tag-button').prop('disabled', true)
        $('#status-button').prop('disabled', true)
        $('#deleterun-button').prop('disabled', true)
    } else {
        $('#select-all').text('indeterminate_check_box');
    }
}

// Allow unchecking of radio buttons in the filter window
// $('input[type=radio]').click(allow_unselect);

function allow_unselect(e){
    if (e.ctrlKey) {
            $(this).prop('checked', false);
        }
}

// ----------------------------------------------------------------------
//  STATUS

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

        run_table.rows('.selected').every( function ( rowIdx, tableLoop, rowLoop ) {
            updateRunStatus(this, new_status.filter(':checked').val());
        });

    }
}

function updateRunStatus(row, status) {
    $.ajax({
        url : script_name+"/api/runs/runs/"+row.data()['pk']+'/',
        type : "PATCH",
        data : { reduction_status: status },

        success : function(json) {
            edit_status_window.dialog( "close" );
            // row.data(json).draw('page');
            $(".fullwidth.dataTable").DataTable().draw('page');
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

// ----------------------------------------------------------------------
//  TAGS

function load_tags() {
    //   Clear tag options of the add-system form
    $("#id_tags").empty();

    //   Load all tags and add them to the window
    $.ajax({
        url : script_name+"/api/tags/",
        type : "GET",
        success : function(json) {
            all_tags = json.results;

            for (var i=0; i<all_tags.length; i++) {
                tag = all_tags[i];

                $('#tagOptions').append("<li title='" + tag['description'] +
                "'><input name='tags' type='checkbox' value='"
                + tag['pk'] + "' /> " + tag['name'] + "</li>" );

                $('#tag_filter_options').append(
                "<li><label><input id='id_status_" + i + "' name='tags' type='radio' value='" +
                tag['pk'] + "' /> " + tag['name'] + "</label></li>");

            }

            $('input[type=radio]').click(allow_unselect);

        },
        error : function(xhr,errmsg,err) {
            console.log(xhr.status + ": " + xhr.responseText);
            all_tags = [];
        }
    });
}

function openTagEditWindow() {
    edit_tags_window = $("#editTags").dialog({
        title: "Add/Remove Tags",
        buttons: { "Update": updateTags},
        // buttons: { "Update": update_run_tags},
        close: function() { edit_tags_window.dialog( "close" ); }
    });

    edit_tags_window.dialog( "open" );
}

function updateTags() {
    // Get the checked tags
    let new_tags = $("input[name='tags']").filter(':checked');
    new_tags = new_tags.map(
        function () { return parseInt(this.value); }
        ).get()

    // Update the tags for each selected observation run
    run_table.rows('.selected').every( function ( rowIdx, tableLoop, rowLoop ) {
        update_run_tags(this, new_tags);
    });

}

function update_run_tags(row, new_tags){
    let run_pk = row.data()['pk'];

    $.ajax({
        url : script_name+"/api/runs/runs/"+run_pk+'/',
        type : "PATCH",
        contentType: "application/json; charset=utf-8",

        data : JSON.stringify({ "tag_ids": new_tags }),

        success : function(json) {
            // update the table and close the edit window
            edit_tags_window.dialog( "close" );
            $(".fullwidth.dataTable").DataTable().draw('page');
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

// ----------------------------------------------------------------------

function deleteRuns(){
    if (confirm('Are you sure you want to delete these Observation runs? This can NOT be undone!')===true){
    let rows = [];
    // get list of files
    run_table.rows('.selected').every(function (rowIdx, tableLoop, rowLoop) {
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
            url : script_name+"/api/runs/runs/"+pk+'/',
            type : "DELETE",
            success : function(json) {
                n += 1;
                run_table.row(row).remove().draw('full-hold');
                $('#select-all').text('check_box_outline_blank');
                $('#tag-button').prop('disabled', true);
                $('#status-button').prop('disabled', true);
                $('#deleterun-button').prop('disabled', true);
                $('#progress-bar').val(n)
            },
            error : function(xhr,errmsg,err) {
                n += 1;
                $('#progress-bar').val(n)
                if (xhr.status === 403){
                    alert('You have to be logged in to delete this observation runs.');
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

// ----------------------------------------------------------------------

// function openAddRunsWindow() {
//    add_runs_window = $("#addRuns").dialog({
//       autoOpen: false,
//       title: "Add Observation run(s)",
//       close: function() { add_runs_window.dialog( "close" ); },
//    });
//
//    add_runs_window.dialog( "open" );
// }
