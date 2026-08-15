Component({
  properties: {
    item: {
      type: Object,
      value: {}
    },
    locationName: {
      type: String,
      value: '-'
    },
    color: {
      type: String,
      value: '#00D2FF'
    }
  },
  methods: {
    onTap() {
      const deviceId = this.data.item?.device?.id
      if (deviceId) {
        wx.navigateTo({
          url: `/pages/device/detail?id=${deviceId}`
        })
      }
    }
  }
})
