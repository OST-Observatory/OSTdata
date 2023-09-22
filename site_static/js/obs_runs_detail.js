
let file_table = null;
let run = {};
let edit_status_window = null;
let edit_tags_window = null;
let all_tags = null;

$(document).ready(function () {

    //  Sanitize ajax calls if the site does not run in the web server root dir
    let script_name = $('#script_name').attr('name');
    if ( script_name == 'None' ) {
        script_name = '';
    }

    // Table functionality
    file_table = $('#datafiletable').DataTable({
        dom: 'l<"toolbar">frtip',
        serverSide: true,
        ajax: {
            url: script_name+'/api/runs/datafiles/?format=datatables&keep=pk,naxis2,dec_dms,ra_hms',
            //adding "&keep=id,rank" will force return of id and rank fields
            data: get_filter_keywords,
            contentType: "application/json; charset=utf-8",
            dataType: "json",
        },
        searching: false,
        orderMulti: false, //Can only order on one column at a time
        order: [2],
        columns: [
            {  orderable:   false,
                className:  'select-control',
                data:       null,
                render:     selection_render,
                width:      '10',
                searchable: false,
            },
            { data: 'file_name', orderable: false },
            // { data: 'hjd' },
            { data: 'obs_date' },
            { data: 'main_target' },
            { data: 'ra', render: coordinates_render },
            { data: 'file_type' },
            { data: 'naxis1', render: size_render, searchable: false, orderable: false },
            // { data: 'naxis1' },
            { data: 'exposure_type_display', orderable: false },
            { data: 'exptime' },
        //       { data: 'datasets', render: dataset_render , searchable: false, orderable: false },
            { data: 'tags', render: tag_render, searchable: false, orderable: false },
        ],
        paging: true,
        pageLength: 20,
        lengthMenu: [[10, 20, 50, 100, 1000], [10, 20, 50, 100, 1000]], // Use -1 for all.
        scrollY: $(window).height() - $('header').outerHeight(true) - 196,
        scrollCollapse: true,
        autoWidth: true,
    });

    //Add toolbar to table
    $("div.toolbar").html(
        "<input id='tag-button'  class='tb-button' value='Edit Tags' type='button' disabled>");

    // Load the tags and add them to the tag selection list, and the tag edit window
    load_tags();

    //  Load the observation run tags info
    let run_id = $('#tag_list').attr('run_id')
    $.ajax({
        url: script_name+"/api/runs/runs/" + run_id + '/',
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
    $( "#tag-button").click( openTagEditWindow );


    //  Initializing tag update window for observation run
    var update_tag_window = $("#tagAdd").dialog({
        autoOpen: false,
        width: 'auto',
        modal: true
    });

    //  Initializing tag update window for data file (table)
    edit_tags_window = $("#editTags").dialog({
        autoOpen: false,
        width: '250',
        modal: true,
    });

    // Check and uncheck tables rows
    $('#datafiletable tbody').on( 'click', 'td.select-control', function () {
        let tr = $(this).closest('tr');
        let row = file_table.row( tr );
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

            file_table.rows().every( function ( rowIdx, tableLoop, rowLoop ) {
                deselect_row(this); // Open this row
            });
        } else {
            // Close all rows
            $(this).text('check_box')

            file_table.rows().every( function ( rowIdx, tableLoop, rowLoop ) {
                select_row(this); // close the row
            });
        }
    });


    //   Reset check boxes when changing number of displayed objects in table
    $('#datafiletable_length').change(function() {
        file_table.rows().every( function (rowIdx, tableLoop, rowLoop) {
            deselect_row(this);
        });
    });

    //   Reset check boxes when switching to the next table page
    $('#datafiletable_paginate').click(function() {
        file_table.rows().every( function (rowIdx, tableLoop, rowLoop) {
            deselect_row(this);
        });
    });
});


// ----------------------------------------------------------------------
// OBSERVATION RUN TAGS

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
    let run_pk = $('#tagEditButton').attr('run_id');

    //  Sanitize ajax calls if the site does not run in the web server root dir
    let script_name = $('#script_name').attr('name');
    if ( script_name == 'None' ) {
        script_name = '';
    }

    $.ajax({
        url: script_name+"/api/runs/runs/" + run_pk + '/',
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

// ----------------------------------------------------------------------
// Table filter functionality

function get_filter_keywords( d ) {
    // let selected_tags = $("#tag_filter_options input:checked").map( function () { return parseInt(this.value); }).get();

    d = $.extend( {}, d, {
        "observation_run": $('#tag_list').attr('run_id'),
        // "name": $('#filter_name').val(),
        // "tags": selected_tags[0],
    } );
    return d
}

// ----------------------------------------------------------------------
// Table renderers

function selection_render( data, type, full, meta ) {
    if ( $(file_table.row(meta['row']).node()).hasClass('selected') ){
        return '<i class="material-icons button select" title="Select">check_box</i>';
    } else {
        return '<i class="material-icons button select" title="Select">check_box_outline_blank</i>';
    }
}

function tag_render( data, type, full, meta ) {
    // Render the tags as a list of divs with the correct color.
    let result = "";
    let tag = data[0];
    for (i = 0; i < data.length; i++) {
        tag = data[i];
        result += "<div class='small-tag' style='border-color:"+tag.color+"' title='"+tag.description+"'>"+tag.name+"</div>";
    }
    return result;
}

function size_render( data, type, full, meta ) {
    //  Render image size
    return data + "x" + full['naxis2'];
}

function coordinates_render( data, type, full, meta ) {
    //  Render coordinates
    return full['ra_hms'] + ' ' + full['dec_dms'];
}

// ----------------------------------------------------------------------
// Selection and Deselection of rows

function select_row(row) {
    $(row.node()).find("i[class*=select]").text('check_box')
    $(row.node()).addClass('selected');
    if ( file_table.rows('.selected').data().length < file_table.rows().data().length ) {
        $('#select-all').text('indeterminate_check_box');
    } else {
        $('#select-all').text('check_box');
    }
    $('#tag-button').prop('disabled', false)
}

function deselect_row(row) {
    $(row.node()).find("i[class*=select]").text('check_box_outline_blank')
    $(row.node()).removeClass('selected');
    if ( file_table.rows('.selected').data().length === 0 ) {
        $('#select-all').text('check_box_outline_blank');
        $('#tag-button').prop('disabled', true)
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
// Edit data file (table) tags functionality

function load_tags() {
    //   Clear tag options of the add-system form
    $("#id_tags").empty();

    //  Sanitize ajax calls if the site does not run in the web server root dir
    let script_name = $('#script_name').attr('name');
    if ( script_name == 'None' ) {
        script_name = '';
    }


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
    file_table.rows('.selected').every( function ( rowIdx, tableLoop, rowLoop ) {
        update_file_tags(this, new_tags);
    });

}

function update_file_tags(row, new_tags){
    //  Sanitize ajax calls if the site does not run in the web server root dir
    let script_name = $('#script_name').attr('name');
    if ( script_name == 'None' ) {
        script_name = '';
    }

    let pk = row.data()['pk']
    $.ajax({
        url : script_name+"/api/runs/datafiles/"+pk+'/',
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
