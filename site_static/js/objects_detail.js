
var run_table = null;


$(document).ready(function () {
    let obj_pk = $('#tagEditButton').attr('obj_id');

    //  Sanitize ajax calls if the site does not run in the web server root dir
    let script_name = $('#script_name').attr('name');
    if ( script_name == 'None' ) {
        script_name = '';
    }

    run_table = $('#runtable').DataTable({
        // dom: 'l<"toolbar">frtip',
        serverSide: true,
        ajax: {
            url: script_name+'/api/objects/'+obj_pk+'/obsruns/?format=datatables&keep=reduction_status_display,n_img,n_ser,start_time,end_time',
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

    //  Load the object tags info
    let object_pk = $('#tag_list').attr('obj_id')
    $.ajax({
        url: script_name+"/api/objects/" + object_pk + '/',
        type: "GET",
        success: function (json) {
            run = json;
            show_tags();
        },
        error: function (xhr, errmsg, err) {
            console.log(xhr.status + ": " + xhr.responseText);
        }
    });

    //  Event listeners
    $("#tagEditButton").click(openTagEditBox);

    //  Initializing tag update window for object
    var update_tag_window = $("#tagAdd").dialog({
        autoOpen: false,
        width: 'auto',
        modal: true
    });


    // Check and uncheck tables rows
    $('#runtable tbody').on( 'click', 'td.select-control', function () {
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

    //   Reset check boxes when changing number of displayed objects in table
    $('#datafiletable_length').change(function() {
        run_table.rows().every( function (rowIdx, tableLoop, rowLoop) {
            deselect_row(this);
        });
    });

    //   Reset check boxes when switching to the next table page
    $('#datafiletable_paginate').click(function() {
        run_table.rows().every( function (rowIdx, tableLoop, rowLoop) {
            deselect_row(this);
        });
    });
});

// ----------------------------------------------------------------------
// Table filter functionality

function get_filter_keywords( d ) {
    // let selected_tags = $("#tag_filter_options input:checked").map( function () { return parseInt(this.value); }).get();

    d = $.extend( {}, d, {
        // "obsrun": $('#tagEditButton').attr('run_id'),
        // "name": $('#filter_name').val(),
        // "tags": selected_tags[0],
    } );
    return d
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
    // $('#deleterun-button').prop('disabled', false)
}

function deselect_row(row) {
    $(row.node()).find("i[class*=select]").text('check_box_outline_blank')
    $(row.node()).removeClass('selected');
    if ( run_table.rows('.selected').data().length === 0 ) {
        $('#select-all').text('check_box_outline_blank');
        $('#tag-button').prop('disabled', true)
        $('#status-button').prop('disabled', true)
        // $('#deleterun-button').prop('disabled', true)
    } else {
        $('#select-all').text('indeterminate_check_box');
    }
}


// Allow unchecking of radio buttons in the filter window
// // $('input[type=radio]').click(allow_unselect);

// function allow_unselect(e){
//     if (e.ctrlKey) {
//             $(this).prop('checked', false);
//         }
// }

// ----------------------------------------------------------------------
// Table filter functionality

function selection_render( data, type, full, meta ) {
    if ( $(run_table.row(meta['row']).node()).hasClass('selected') ){
        return '<i class="material-icons button select" title="Select">check_box</i>';
    } else {
        return '<i class="material-icons button select" title="Select">check_box_outline_blank</i>';
    }
}

function name_render( data, type, full, meta ) {
    // Create a link to the detail for the observation run name
    let start = full['start_time'].split('.')[0];
    let end = full['end_time'].split(" ")[1].split('.')[0];
    let href = "<a href='"+full['href']+"'>"+start+'-'+end+"</a>";
    return href;
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
// TAGS

//  Check which tags should be displayed in the tag window, and check the
//  included tags in the tag edit window.
function show_tags() {
    $('#tag_list').empty(); // remove all existing tags
    for (i = 0; i < run.tags.length; i++) {
        let tag = run.tags[i];
        $('#tag_pk_' + tag.pk).prop("checked", true);
        $('#tag_list').append(
            "<div class='tag' id='tag-" + tag.pk + "' style='border-color:" + tag.color + "' title='" + tag.info + "'>" + tag.name + "</div>"
        );
    }

}

//  Open window to add/modify/change tags
function openTagEditBox() {
    update_tag_window = $("#tagAdd").dialog({
        buttons: {"Update": update_tags},
        close: function () {
            update_tag_window.dialog("close");
        }
    });

    update_tag_window.dialog("open");
}

// Update the tags attached to this observation run
function update_tags() {
    let new_tags = $("#tagOptionsRun input:checked").map(
        function () {
            return this.value;
        }).get();
    let object_pk = $('#tagEditButton').attr('obj_id');
    $.ajax({
        url: script_name+"/api/objects/" + object_pk + '/',
        type: "PATCH",
        contentType: "application/json; charset=utf-8",

        data: JSON.stringify({"tag_ids": new_tags}),

        success: function (json) {
            // update the tags of the star variable, and update the page
            run.tags = json.tags;
            show_tags();
            update_tag_window.dialog("close");
        },

        error: function (xhr, errmsg, err) {
            console.log(xhr.status + ": " + xhr.responseText);
        }
    });
}
