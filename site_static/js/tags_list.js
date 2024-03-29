
var tag_table = null;

$(document).ready(function () {

    //  Sanitize ajax calls if the site does not run in the web server root dir
    let script_name = $('#script_name').attr('name');
    if ( script_name == 'None' ) {
        script_name = '';
    }

   // Table functionality
   tag_table = $('#tagtable').DataTable({
   //    autoWidth: true,
   //    paging: false,
   //    info: false,
      serverSide: true,
      ajax: {
         url: script_name+'/api/tags/?format=datatables',
      },
      columns: [
         { data: 'name' },
         { data: 'description' },
         { data: 'color', render: color_render},
         { data: 'pk', render: action_render, width: '100',
         className: 'dt-center', visible: user_authenticated},
      ],
   });

   function color_render( data, type, full, meta ) {
      // Render the tags as a list of divs with the correct color.
      return "<div class='circle block' style='background:"+data+"'></div>" + data
   }

   function action_render( data, type, full, meta ) {
      // Add edit and delete buttons
      return "<i class='material-icons button delete' id='delete-tag-"+data+"'>delete</i>" +
               "<i class='material-icons button edit' id='edit-tag-"+data+"'>edit</i>"
   }

   // Initializing the dialog window
   var tag_window = $("#addEditTag").dialog({
      autoOpen: false,
      width: 'auto',
      modal: true
   });

   // add event listeners
   $( ".tagAddButton").click( openTagAddBox );
   $("#tagtable").on('click', 'i[id^=edit-tag-]', function() {
      var closestRow = $(this).closest('tr');
      var data = tag_table.row(closestRow).data();
      openTagEditBox(closestRow, data);
   });
   $("#tagtable").on('click', 'i[id^=delete-tag-]', function() {
      var closestRow = $(this).closest('tr');
      var data = tag_table.row(closestRow).data();
      deleteTag(closestRow, data);
   });

});

// Add new tag
function openTagAddBox() {

   tag_window = $("#addEditTag").dialog({
      title: 'Add new tag',
      buttons: { "Add": addTag },
      close: function() { tag_window.dialog( "close" ); }
   });

   tag_window.dialog( "open" );
};

function addTag() {
    //  Sanitize ajax calls if the site does not run in the web server root dir
    let script_name = $('#script_name').attr('name');
    if ( script_name == 'None' ) {
        script_name = '';
    }

   $.ajax({
      url : script_name+"/api/tags/",
      type : "POST",
      data : {
         name :        $('#tag-name').val(),
         description : $('#tag-description').val(),
         color :       $('#tag-color').val(),
      },

      success : function(json) {
            tag_window.dialog( "close" );
            tag_table.row.add( json ).draw();
      },

      error : function(xhr,errmsg,err) {
            console.log(xhr.status + ": " + xhr.responseText);
      }
   });

};

// Edit method
function openTagEditBox(tabelrow, data) {
   tag_window = $("#addEditTag").dialog({
      title: 'Edit tag',
      buttons: { "Update": function () { editTag(tabelrow, data); } },
      close: function() { tag_window.dialog( "close" ); }
   });

   tag_window.dialog( "open" );
   $("#tag-name").val( data['name'] );
   $("#tag-description").val( data['description'] );
   $("#tag-color").val( data['color'] );
};

function editTag(tabelrow, data) {
    //  Sanitize ajax calls if the site does not run in the web server root dir
    let script_name = $('#script_name').attr('name');
    if ( script_name == 'None' ) {
        script_name = '';
    }

   $.ajax({
      url : script_name+"/api/tags/"+data['pk']+'/',
      type : "PATCH",
      data : {
         name :        $('#tag-name').val(),
         description : $('#tag-description').val(),
         color :       $('#tag-color').val(),
      },

      success : function(json) {
         tag_window.dialog( "close" );
         tag_table.row(tabelrow).data(json).draw();
      },

      error : function(xhr,errmsg,err) {
         console.log(xhr.status + ": " + xhr.responseText);
      }
   });
};

// Delete method
function deleteTag(tabelrow, data) {
    //  Sanitize ajax calls if the site does not run in the web server root dir
    let script_name = $('#script_name').attr('name');
    if ( script_name == 'None' ) {
        script_name = '';
    }

   if (confirm('Are you sure you want to remove this Tag?')==true){
      $.ajax({
            url : script_name+"/api/tags/"+data['pk']+'/',
            type : "DELETE",
            success : function(json) {
               // remove the row from the table
               tag_table.row(tabelrow).remove().draw();
            },

            error : function(xhr,errmsg,err) {
               console.log(xhr.status + ": " + xhr.responseText);
            }
      });
   };
};
