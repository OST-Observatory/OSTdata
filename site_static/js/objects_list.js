
let object_table = null;
let edit_tags_window = null;
let all_tags = null;


$(document).ready(function () {

    //  Sanitize ajax calls if the site does not run in the web server root dir
    let script_name = $('#script_name').attr('name');
    if ( script_name == 'None' ) {
        script_name = '';
    }

    object_table = $('#datatable').DataTable({
        dom: 'l<"toolbar">frtip',
        serverSide: true,
        ajax: {
            url: script_name+'/api/objects/?format=datatables&keep=pk,href,dec_dms,ra_hms',
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
            { data: 'ra', render: coordinates_render },
            // { data: 'class' },
            // { data: 'gmag' },
            { data: 'obsrun', render: obsrun_render },
            { data: 'tags', render: tag_render , searchable: false, orderable: false },
        ],
        paging: true,
        pageLength: 50,
        lengthMenu: [[10, 20, 50, 100, 1000], [10, 20, 50, 100, 1000]], // Use -1 for all.
        scrollY: $(window).height() - $('header').outerHeight(true) - 196,
        scrollCollapse: true,
        autoWidth: true,
    });

    //  Add toolbar to table
    if (user_authenticated) {
        $("div.toolbar").html(
            "<input id='tag-button'  class='tb-button' value='Edit Tags' type='button' disabled>");
    };

    // Load the tags and add them to the tag selection list, and the tag edit window
    load_tags();

    // Event listener to the two range filtering inputs to redraw on input
    $('#filter-form').submit( function(event) {
        event.preventDefault();
        object_table.draw();
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
        let row = object_table.row( tr );
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

            object_table.rows().every( function ( rowIdx, tableLoop, rowLoop ) {
                deselect_row(this); // Open this row
            });
        } else {
            // Close all rows
            $(this).text('check_box')

            object_table.rows().every( function ( rowIdx, tableLoop, rowLoop ) {
                select_row(this); // close the row
            });
        }
    });

    //   Initialize edit windows
    edit_tags_window = $("#editTags").dialog({
        autoOpen: false,
        width: '250',
        modal: true,
    });

    //   Event listeners for edit buttons
    $( "#tag-button").click( openTagEditWindow );


    //   Reset check boxes when changing number of displayed objects in table
    $('#datatable_length').change(function() {
        object_table.rows().every( function (rowIdx, tableLoop, rowLoop) {
            deselect_row(this);
        });
    });

    //   Reset check boxes when switching to the next table page
    $('#datatable_paginate').click(function() {
        object_table.rows().every( function (rowIdx, tableLoop, rowLoop) {
            deselect_row(this);
        });
    });
});

// ----------------------------------------------------------------------
// Table filter functionality

function get_filter_keywords( d ) {
    let selected_tags = $("#tag_filter_options input:checked").map( function () { return parseInt(this.value); }).get();

    d = $.extend( {}, d, {
        "name": $('#filter_name').val(),
        "ra": $('#filter_ra').val(),
        "dec": $('#filter_dec').val(),
        "obs_run": $('#filter_obs_run').val(),
        "tags": selected_tags[0],
    } );

    return d
}

// ----------------------------------------------------------------------
// Table renderers

function selection_render( data, type, full, meta ) {
    if ( $(object_table.row(meta['row']).node()).hasClass('selected') ){
        return '<i class="material-icons button select" title="Select">check_box</i>';
    } else {
        return '<i class="material-icons button select" title="Select">check_box_outline_blank</i>';
    }
}

function name_render( data, type, full, meta ) {
    // Create a link to the detail page
    let href = "<a href='"+full['href']+"'>"+data+"</a>";
    return href;
}

function obsrun_render( data, type, full, meta ) {
    // Render the observation runs as a list with the corresponding date
    let results = [];
    for (i = 0; i < data.length; i++) {
        let run = data[i];
        let href = run.href;
        let name = run.name;
        if ( name.indexOf('-') == -1 ) {
            name = name.slice(0,4)+'-'+name.slice(4,6)+'-'+name.slice(6,8);
        }
        results.push("<a href='"+href+"'> "+name+"</a>");
    }
   return results;
}

function coordinates_render( data, type, full, meta ) {
    //  Render coordinates
    return full['ra_hms'] + ' ' + full['dec_dms'];
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

// ----------------------------------------------------------------------
// Selection and Deselection of rows

function select_row(row) {
    $(row.node()).find("i[class*=select]").text('check_box')
    $(row.node()).addClass('selected');
    if ( object_table.rows('.selected').data().length < object_table.rows().data().length ) {
        $('#select-all').text('indeterminate_check_box');
    } else {
        $('#select-all').text('check_box');
    }
    $('#tag-button').prop('disabled', false)
    // $('#status-button').prop('disabled', false)
}

function deselect_row(row) {
    $(row.node()).find("i[class*=select]").text('check_box_outline_blank')
    $(row.node()).removeClass('selected');
    if ( object_table.rows('.selected').data().length === 0 ) {
        $('#select-all').text('check_box_outline_blank');
        $('#tag-button').prop('disabled', true)
        // $('#status-button').prop('disabled', true)
    } else {
        $('#select-all').text('indeterminate_check_box');
    }
}

function allow_unselect(e){
    if (e.ctrlKey) {
            $(this).prop('checked', false);
        }
}

// ----------------------------------------------------------------------
//  TAGS

function load_tags() {
    console.log('innn');
    //  Sanitize ajax calls if the site does not run in the web server root dir
    let script_name = $('#script_name').attr('name');
    if ( script_name == 'None' ) {
        script_name = '';
    }

      // Clear tag options of the add-system form
    // $("#id_tags").empty();
    console.log('script_name', script_name);

      // Load all tags and add them to the window
    $.ajax({
        url : script_name+"/api/tags/",
        type : "GET",
        success : function(json) {
            all_tags = json.results;

            for (var i=0; i<all_tags.length; i++) {
                tag = all_tags[i];

                console.log('tags', tag);
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
    object_table.rows('.selected').every( function ( rowIdx, tableLoop, rowLoop ) {
        update_objects_tags(this, new_tags);
    });

}

function update_objects_tags(row, new_tags){
    //  Sanitize ajax calls if the site does not run in the web server root dir
    let script_name = $('#script_name').attr('name');
    if ( script_name == 'None' ) {
        script_name = '';
    }

    let pk = row.data()['pk']

    $.ajax({
        url : script_name+"/api/objects/"+pk+'/',
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

// ----------------------------------------------------------------------

// Allow unchecking of radio buttons in the filter window
// $('input[type=radio]').click(allow_unselect);
